from django.db.models import Q, Case, When, Value, IntegerField
from django.utils.timezone import now
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from accounts.auth import CustomJWTAuthentication
from accounts.permissions import IsGymManager, IsPlatformAdmin
from gyms.models import Gym, MemberShip, InOut, MemberShipType, GymBanner, Closet
from gyms.serializers import CustomerPanelGymSerializer, CustomerPanelMembershipSerializer, \
    CustomerPanelInOutRequestSerializer, CustomerPanelGymSerializer, CustomerPanelMemberShipCreateSerializer, \
    GymPanelGymSerializer, GymChoicesSerializer, GymPanelMemberShipTypeSerializer, GymPanelGymBannerSerializer, \
    CustomerPanelSignedGymListSerializer, CustomerPanelInOutSerializer, AdminPanelGymListSerializer, \
    GymPanelInOutSerializer, \
    GymPanelClosetSerializer, GymPanelInOutUpdateSerializer


# Create your views here.
class GymChoices(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        serializer = GymChoicesSerializer(instance={}, context={'request': request})
        return Response(serializer.data)


# <=================== Customer Views ===================>
class CustomerPanelGymList(generics.ListAPIView):
    serializer_class = CustomerPanelGymSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def get_queryset(self):
        customer = getattr(self.request.user, "customer", None)
        if not customer or not customer.gender:
            return Gym.objects.none()  # اگر جنسیت مشتری مشخص نبود

        return Gym.objects.filter(
            Q(gender="both") | Q(gender=customer.gender)
        )


class CustomerPanelGymDetail(generics.RetrieveAPIView):
    queryset = Gym.objects.filter(is_active=True)
    serializer_class = CustomerPanelGymSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]


class CustomerPanelSingedGymList(generics.ListAPIView):
    serializer_class = CustomerPanelSignedGymListSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def get_queryset(self):
        customer = getattr(self.request.user, "customer", None)
        if not customer:
            return Gym.objects.none()
        return Gym.objects.filter(memberships__customer=customer, is_active=True).distinct()

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if not queryset.exists():
            raise NotFound(detail="هیچ باشگاهی ثبت نام نشده است")
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CustomerPanelSignedGymDetail(generics.RetrieveAPIView):
    serializer_class = CustomerPanelGymSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'pk'

    def get_queryset(self):
        customer = getattr(self.request.user, "customer", None)
        if not customer:
            return Gym.objects.none()
        return Gym.objects.filter(memberships__customer=customer, is_active=True).distinct()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class CustomerPanelRequestGymEntry(generics.CreateAPIView):
    serializer_class = CustomerPanelInOutRequestSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def perform_create(self, serializer):
        user = self.request.user
        customer = getattr(user, "customer", None)
        if not customer:
            raise ValidationError("فقط مشتریان می‌توانند درخواست ورود بدهند.")

        gym_id = self.request.data.get("gym")
        if not gym_id:
            raise ValidationError("باشگاه الزامی است.")

        try:
            gym = Gym.objects.get(id=gym_id)
        except Gym.DoesNotExist:
            raise ValidationError("باشگاه مورد نظر یافت نشد.")

        # بررسی InOut باز
        if InOut.objects.filter(
                customer=customer,
                gym=gym
        ).filter(
            Q(confirm_in=False) |
            Q(enter_time__isnull=False, out_time__isnull=True)
        ).exists():
            raise ValidationError("شما یک درخواست ورود فعال دارید، تا زمان خروج نمی‌توانید درخواست جدید ثبت کنید.")

        # بررسی ممبرشیپ فعال
        membership = MemberShip.objects.filter(
            customer=customer,
            gym=gym,
            session_left__gt=0,
            validity_date__gte=now().date()
        ).first()

        if not membership:
            raise ValidationError("شما ممبرشیپ فعال برای این باشگاه ندارید.")

        # ساخت رکورد
        serializer.save(customer=customer, gym=gym, subscription=membership)


class CustomerPanelMembershipListView(generics.ListAPIView):
    serializer_class = CustomerPanelMembershipSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def get_queryset(self):
        if hasattr(self.request.user, "customer"):
            customer = self.request.user.customer
            today = now().date()

            queryset = MemberShip.objects.filter(customer=customer)

            # Annotate با status عددی برای مرتب‌سازی
            queryset = queryset.annotate(
                is_active=Case(
                    When(session_left__gt=0, validity_date__gte=today, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField()
                )
            ).order_by('-is_active', 'validity_date')

            return queryset


class CustomerPanelMembershipDetailView(generics.RetrieveAPIView):
    serializer_class = CustomerPanelMembershipSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    lookup_field = 'pk'

    def get_queryset(self):
        if hasattr(self.request.user, "customer"):
            customer = self.request.user.customer
            today = now().date()

            queryset = MemberShip.objects.filter(customer=customer)

            # Annotate با status عددی برای مرتب‌سازی
            queryset = queryset.annotate(
                is_active=Case(
                    When(session_left__gt=0, validity_date__gte=today, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField()
                )
            ).order_by('-is_active', 'validity_date')

            return queryset


class CustomerMembershipSignUp(generics.CreateAPIView):
    queryset = MemberShip.objects.all()
    serializer_class = CustomerPanelMemberShipCreateSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]


class CustomerPanelInOutList(generics.ListAPIView):
    serializer_class = CustomerPanelInOutSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def get_queryset(self):
        if hasattr(self.request.user, "customer"):
            customer = self.request.user.customer
            qs = InOut.objects.filter(customer=customer, confirm_in=True)
            return qs
        return None


# <=================== Gym Views ===================>
class GymPanelGym(generics.ListCreateAPIView):
    serializer_class = GymPanelGymSerializer
    permission_classes = [IsAuthenticated, IsGymManager]
    authentication_classes = [CustomJWTAuthentication]

    def get_queryset(self):
        return Gym.objects.filter(manager__user=self.request.user)


class GymPanelGymDetail(generics.RetrieveUpdateAPIView):
    """
{
    "title": "باشگاه فیتنو جدید",
    "description": "به‌روز شده توسط مدیر",
    "images": [
        {"id": 2, "image": "data:image/png;base64,..."},  // ویرایش تصویر
        {"image": "data:image/png;base64,..."}             // اضافه کردن تصویر جدید
    ]
}
اگر ID تصویری رو نفرستی و فقط image بدی → تصویر جدید ساخته میشه.
اگر ID تصویر رو نفرستی ولی اون تصویر دیگه در لیست نباشه → حذف میشه.
    """
    serializer_class = GymPanelGymSerializer
    permission_classes = [IsAuthenticated, IsGymManager]
    authentication_classes = [CustomJWTAuthentication]

    def get_queryset(self):
        return Gym.objects.filter(manager__user=self.request.user)

    def perform_update(self, serializer):
        gym = serializer.save()
        return gym


class GymPanelMemberShipType(generics.ListCreateAPIView):
    serializer_class = GymPanelMemberShipTypeSerializer
    permission_classes = [IsAuthenticated, IsGymManager]
    authentication_classes = [CustomJWTAuthentication]

    def get_queryset(self):
        """
        فقط عضویت‌هایی که مربوط به باشگاه‌های متعلق به مدیر فعلی هستند
        """
        return MemberShipType.objects.filter(gyms__manager__user=self.request.user)


class GymPanelMemberShipTypeDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = GymPanelMemberShipTypeSerializer
    permission_classes = [IsAuthenticated, IsGymManager]
    authentication_classes = [CustomJWTAuthentication]

    def get_queryset(self):
        """
        فقط عضویت‌هایی که متعلق به باشگاه‌های خود کاربر هستند
        """
        return MemberShipType.objects.filter(gyms__manager__user=self.request.user)


class GymPanelGymBanner(generics.ListCreateAPIView):
    serializer_class = GymPanelGymBannerSerializer
    permission_classes = [IsAuthenticated, IsGymManager]
    authentication_classes = [CustomJWTAuthentication]

    def get_queryset(self):
        """
        فقط بنرهای مربوط به باشگاه‌های متعلق به مدیر فعلی
        """
        return GymBanner.objects.filter(gym__manager__user=self.request.user)


class GymPanelGymBannerDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = GymPanelGymBannerSerializer
    permission_classes = [IsAuthenticated, IsGymManager]
    authentication_classes = [CustomJWTAuthentication]

    def get_queryset(self):
        """
        فقط بنرهای متعلق به باشگاه‌های مدیر فعلی
        """
        return GymBanner.objects.filter(gym__manager__user=self.request.user)


class GymPanelInOutList(generics.ListAPIView):
    serializer_class = GymPanelInOutSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = InOut.objects.all()

        if hasattr(user, 'gym_manager'):
            gyms = user.gym_manager.gyms.all()
            queryset = queryset.filter(gym__in=gyms)

        elif hasattr(user, 'gym_secretary'):
            queryset = queryset.filter(gym=user.gym_secretary.gym)

        return queryset


class GymPanelInOutPendingList(generics.ListAPIView):
    serializer_class = GymPanelInOutSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = InOut.objects.filter(enter_time__isnull=False, confirm_in=False)

        if hasattr(user, 'gym_manager'):
            # کاربر مدیر باشگاه است
            gyms = user.gym_manager.gyms.all()
            queryset = queryset.filter(gym__in=gyms)

        elif hasattr(user, 'gym_secretary'):
            # کاربر منشی باشگاه است
            queryset = queryset.filter(gym=user.gym_secretary.gym)

        return queryset


class GymPanelInOutUpdate(generics.GenericAPIView):
    queryset = InOut.objects.select_related('gym', 'subscription', 'customer__user', 'closet')
    serializer_class = GymPanelInOutUpdateSerializer
    permission_classes = [IsAuthenticated]

    def patch(self, request, *args, **kwargs):
        inout = self.get_object()
        user = request.user

        # بررسی دسترسی به InOut
        if hasattr(user, 'gym_manager'):
            gyms = user.gym_manager.gyms.all()
            if inout.gym not in gyms:
                return Response({"detail": "شما به این ورود/خروج دسترسی ندارید."}, status=status.HTTP_403_FORBIDDEN)

        elif hasattr(user, 'gym_secretary'):
            if inout.gym != user.gym_secretary.gym:
                return Response({"detail": "این ورود/خروج متعلق به باشگاه شما نیست."}, status=status.HTTP_403_FORBIDDEN)

        else:
            return Response({"detail": "فقط مدیر یا منشی باشگاه مجاز به انجام این عملیات هستند."},
                            status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(inout, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            "message": "عملیات با موفقیت انجام شد.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


class GymPanelClosetList(generics.ListAPIView):
    serializer_class = GymPanelClosetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Closet.objects.select_related('gym')

        if hasattr(user, 'gym_manager'):
            gyms = user.gym_manager.gyms.all()
            queryset = queryset.filter(gym__in=gyms)

        elif hasattr(user, 'gym_secretary'):
            queryset = queryset.filter(gym=user.gym_secretary.gym)

        # اگر خواستی می‌تونی اینجا ordering هم اضافه کنی، مثلاً بر اساس gym و number
        return queryset.order_by('gym__title', 'number')


# <=================== Admin Views ===================>
class AdminPanelGymList(generics.ListAPIView):
    queryset = Gym.objects.all()
    serializer_class = AdminPanelGymListSerializer
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    authentication_classes = [CustomJWTAuthentication]
