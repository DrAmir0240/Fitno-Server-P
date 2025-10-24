import secrets
from datetime import timedelta

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from Fitno import settings
from accounts.auth import CustomJWTAuthentication
from accounts.models import Customer, GymManager, OTP, User, APIKey
from accounts.permissions import IsGymManager, IsPlatformAdmin
from accounts.serializers import CustomerRegisterSerializer, PasswordLoginSerializer, GymManagerSerializer, \
    GymSerializer, UserRoleStatusSerializer, CustomerProfileSerializer, GymPanelCustomerListSerializer, \
    VerifyOTPSerializer, VerifyOTPResponseSerializer, RequestOTPSerializer, RequestOTPResponseSerializer, \
    AdminPanelCustomerDetailSerializer, GymPanelCustomerDetailSerializer, ResetPasswordWithOTPSerializer, \
    RequestOTPAuthenticatedSerializer, GymPanelRequestOTPForCustomerSerializer, GymPanelVerifyAndRegisterSerializer, \
    AdminPanelCustomerCreateSerializer, GymPanelCustomerChoicesSerializer
from gyms.models import Gym, MemberShip, MemberShipType


# Create your views here.
# <=================== User Views ===================>
class UserRoleStatusView(generics.GenericAPIView):
    serializer_class = UserRoleStatusSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        if user.is_authenticated:
            data = {
                "is_authenticated": True,
                "name": user.full_name,
                "is_customer": hasattr(user, "customer"),
                "is_gym_manager": hasattr(user, "gym_manager"),
                "is_platform_manager": hasattr(user, "platform_manager"),
                "phone_number": user.phone,
            }
        else:
            data = {
                "is_authenticated": False,
                "name": None,
                "is_customer": False,
                "is_gym_manager": False,
                "is_platform_manager": False,
                "phone_number": None,
            }

        serializer = self.get_serializer(data)
        return Response(serializer.data)


class LogoutView(generics.GenericAPIView):
    """
    ویو لاگ اوت یک درخواست پست با بادی خالی
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def post(self, request):
        try:
            refresh_token = request.COOKIES.get('refresh_token')
            if refresh_token is None:
                return Response({"error": "Refresh token not found."}, status=status.HTTP_400_BAD_REQUEST)

            token = RefreshToken(refresh_token)
            token.blacklist()

            response = Response({"message": "Logout successful"}, status=status.HTTP_200_OK)
            # پاک کردن کوکی‌ها
            response.delete_cookie('access_token')
            response.delete_cookie('refresh_token')
            return response

        except TokenError:
            return Response({"error": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)


class LoginView(generics.GenericAPIView):
    serializer_class = PasswordLoginSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        customer = user.customer

        # ساخت توکن‌ها
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        response_data = {
            "user_id": user.id,
            "phone": user.phone,
            "full_name": user.full_name,
            "email": user.email,
            "national_code": customer.national_code,
            "city": customer.city,
            "refresh": refresh_token,
            "access": access_token,
        }

        response = Response(response_data, status=status.HTTP_200_OK)

        # ست کردن کوکی‌ها
        response.set_cookie(
            key=settings.SIMPLE_JWT["AUTH_COOKIE"],
            value=access_token,
            httponly=True,
            secure=settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", False),
            samesite=settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE", "Lax"),
            max_age=settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds(),
        )

        response.set_cookie(
            key=settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"],
            value=refresh_token,
            httponly=True,
            secure=settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", False),
            samesite=settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE", "Lax"),
            max_age=settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds(),
        )

        return response


class RequestOTPView(generics.GenericAPIView):
    serializer_class = RequestOTPSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @extend_schema(
        request=RequestOTPSerializer,
        responses={
            200: RequestOTPResponseSerializer,
            400: RequestOTPResponseSerializer,
            403: RequestOTPResponseSerializer,
            500: RequestOTPResponseSerializer
        },
        description="ارسال درخواست OTP با شماره موبایل"
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data.get('phone')

        user = User.objects.filter(phone=phone).first()
        if not user:
            return Response(
                {"error": "این شماره وجود ندارد"},
                status=status.HTTP_404_NOT_FOUND
            )

        OTP.objects.filter(user=user).delete()
        otp_code = str(secrets.randbelow(100000)).zfill(5)
        expires_at = timezone.now() + timedelta(minutes=2)
        otp = OTP.objects.create(user=user, code=otp_code, expires_at=expires_at)
        success, message = otp.send_otp(phone=phone, otp_code=otp_code)

        if not success:
            return Response(
                {"error": f"خطا در ارسال OTP: {message}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        return Response({"message": "لطفاً کد OTP را وارد کنید"}, status=status.HTTP_200_OK)


class VerifyOTPView(generics.GenericAPIView):
    serializer_class = VerifyOTPSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @extend_schema(
        request=VerifyOTPSerializer,
        responses={
            200: VerifyOTPResponseSerializer,
            400: VerifyOTPResponseSerializer,
            403: VerifyOTPResponseSerializer,
            404: VerifyOTPResponseSerializer
        },
        description="تأیید کد OTP و دریافت توکن‌های دسترسی"
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        api_key = request.headers.get('X-API-Key')
        if not api_key or not APIKey.objects.filter(key=api_key, is_active=True).exists():
            return Response({"error": "Invalid API Key"}, status=status.HTTP_403_FORBIDDEN)

        phone = serializer.validated_data.get('phone')
        code = serializer.validated_data.get('code')

        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            otp = OTP.objects.filter(user=user).latest('created_at')
            if otp.code != code or not otp.is_valid():
                return Response({"error": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)
            otp.delete()
            if not user.is_active:
                user.is_active = True
                user.save()
        except OTP.DoesNotExist:
            return Response({"error": "No OTP found"}, status=status.HTTP_400_BAD_REQUEST)

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        response = Response({"message": "Login successful"}, status=status.HTTP_200_OK)
        response.set_cookie(
            key='access_token',
            value=access_token,
            httponly=True,
            secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
            samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE'],
            max_age=int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds())
        )
        response.set_cookie(
            key='refresh_token',
            value=refresh_token,
            httponly=True,
            secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
            samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE'],
            max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds())
        )
        return response


class RefreshTokenView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'])
        if not refresh_token:
            return Response({"detail": "Refresh token not found in cookies"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            refresh = RefreshToken(refresh_token)  # refresh_token از کوکی گرفته میشه
            access_token = str(refresh.access_token)  # فقط اکسس جدید ساخته میشه

            response = Response({
                "access": access_token
            }, status=status.HTTP_200_OK)

            # فقط اکسس توکن جدید تو کوکی ست میشه
            response.set_cookie(
                key=settings.SIMPLE_JWT['AUTH_COOKIE'],
                value=access_token,
                httponly=True,
                secure=settings.SIMPLE_JWT.get('AUTH_COOKIE_SECURE', False),
                samesite=settings.SIMPLE_JWT.get('AUTH_COOKIE_SAMESITE', 'Lax'),
                max_age=settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds(),
            )

            return response

        except Exception:
            return Response({"detail": "Invalid or expired refresh token"}, status=status.HTTP_401_UNAUTHORIZED)


class RequestOTPAuthenticatedView(generics.GenericAPIView):
    """
    ارسال OTP برای کاربر احراز هویت شده.
    شماره موبایل از request.user.pho گرفته می‌شود و نباید در بدنهٔ POST فرستاده شود.
    """
    serializer_class = RequestOTPAuthenticatedSerializer
    permission_classes = [IsAuthenticated]

    # پاسخ‌ها از همین serializer مشترک استفاده میشه:
    @extend_schema(
        request=RequestOTPAuthenticatedSerializer,
        responses={
            200: RequestOTPResponseSerializer,
            400: RequestOTPResponseSerializer,
            401: RequestOTPResponseSerializer,
            500: RequestOTPResponseSerializer
        },
        description="ارسال درخواست OTP برای کاربر لاگین شده (شماره از request.user گرفته می‌شود)"
    )
    def post(self, request, *args, **kwargs):
        # اعتبارسنجی بدنه (هرچند خالیه) برای استفاده از raise_exception و مستندسازی
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not getattr(user, "phone", None):
            return Response(
                {"error": "شماره تلفن برای این کاربر ثبت نشده است"},
                status=status.HTTP_400_BAD_REQUEST
            )

        phone = user.phone  # مثال: "0912......"

        # حذف OTPهای قبلی (مثل نسخهٔ قبلی)
        OTP.objects.filter(user=user).delete()

        # تولید کد و ذخیره
        otp_code = str(secrets.randbelow(100000)).zfill(5)
        expires_at = timezone.now() + timedelta(minutes=2)
        otp = OTP.objects.create(user=user, code=otp_code, expires_at=expires_at)

        # ارسال پیامک
        success, message = otp.send_otp(phone=phone, otp_code=otp_code)
        if not success:
            return Response(
                {"error": f"خطا در ارسال OTP: {message}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            {"message": "کد OTP با موفقیت ارسال شد. لطفاً آن را استفاده کنید."},
            status=status.HTTP_200_OK
        )


class ResetPasswordWithOTPView(generics.GenericAPIView):
    serializer_class = ResetPasswordWithOTPSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ResetPasswordWithOTPSerializer,
        responses={
            200: {"message": "رمز عبور با موفقیت تغییر کرد"},
            400: {"error": "ورودی نامعتبر"},
            401: {"error": "احراز هویت لازم است"},
        },
        description="ریست پسورد با استفاده از کد OTP؛ شماره از کاربر احراز هویت شده گرفته می‌شود"
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": "رمز عبور با موفقیت تغییر کرد"}, status=status.HTTP_200_OK)


# <=================== Customer Views ===================>
class CustomerRegisterView(generics.CreateAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerRegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return Response(
                {"detail": "شما قبلاً ثبت‌نام کرده‌اید و وارد شده‌اید."},
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()

        # توکن‌ها
        refresh = RefreshToken.for_user(customer.user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        response_data = serializer.data
        response_data["access"] = access_token
        response_data["refresh"] = refresh_token

        response = Response(response_data, status=status.HTTP_201_CREATED)

        # ست کردن کوکی‌ها
        response.set_cookie(
            key=settings.SIMPLE_JWT['AUTH_COOKIE'],
            value=access_token,
            httponly=True,
            secure=settings.SIMPLE_JWT.get('AUTH_COOKIE_SECURE', False),
            samesite=settings.SIMPLE_JWT.get('AUTH_COOKIE_SAMESITE', 'Lax'),
            max_age=settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds(),
        )

        response.set_cookie(
            key=settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'],
            value=refresh_token,
            httponly=True,
            secure=settings.SIMPLE_JWT.get('AUTH_COOKIE_SECURE', False),
            samesite=settings.SIMPLE_JWT.get('AUTH_COOKIE_SAMESITE', 'Lax'),
            max_age=settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds(),
        )

        return response


class CustomerProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = CustomerProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        if hasattr(self.request.user, 'customer'):
            return self.request.user.customer


# <=================== GymManager Views ===================>
class GymManagerRegisterView(generics.CreateAPIView):
    queryset = GymManager.objects.all()
    serializer_class = GymManagerSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]


class FirstGymAddView(generics.CreateAPIView):
    queryset = Gym.objects.all()
    serializer_class = GymSerializer
    permission_classes = [IsGymManager]
    authentication_classes = [CustomJWTAuthentication]


class GymPanelCustomerListView(generics.ListAPIView):
    serializer_class = GymPanelCustomerListSerializer
    permission_classes = [IsGymManager, IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'gym_secretary'):
            gym = user.gym_secretary.gym
            return Customer.objects.filter(memberships__gym=gym).distinct()

        elif hasattr(user, 'gym_manager'):
            gyms = user.gym_manager.gyms.all()
            return Customer.objects.filter(memberships__gym__in=gyms).distinct()

        return Customer.objects.none()


class GymPanelCustomerDetailView(generics.RetrieveAPIView):
    serializer_class = GymPanelCustomerDetailSerializer
    permission_classes = [IsGymManager]
    authentication_classes = [CustomJWTAuthentication]

    def get_queryset(self):
        user = self.request.user

        if hasattr(user, 'gym_secretary'):
            gym = user.gym_secretary.gym
            return Customer.objects.filter(memberships__gym=gym).distinct()

        elif hasattr(user, 'gym_manager'):
            gyms = user.gym_manager.gyms.all()
            return Customer.objects.filter(memberships__gym__in=gyms).distinct()

        return Customer.objects.none()


class GymPanelCustomerChoicesView(generics.ListAPIView):
    serializer_class = GymPanelCustomerChoicesSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # اگر کاربر مدیر باشگاه است
        if hasattr(user, 'gym_manager'):
            manager = user.gym_manager
            # فرض بر اینه که هر مدیر فقط یک باشگاه دارد
            gyms = Gym.objects.filter(manager=manager)
            return MemberShipType.objects.filter(gyms__in=gyms)

        # اگر کاربر منشی باشگاه است
        elif hasattr(user, 'gym_secretary'):
            secretary = user.gym_secretary
            return MemberShipType.objects.filter(gyms=secretary.gym)

        # اگر نه مدیر است و نه منشی
        else:
            raise PermissionDenied("شما دسترسی به مشاهده این اطلاعات را ندارید.")


class GymPanelRequestOTPView(generics.GenericAPIView):
    serializer_class = GymPanelRequestOTPForCustomerSerializer
    permission_classes = []  # AllowAny

    @extend_schema(
        request=RequestOTPSerializer,
        responses={200: {"message": "کد تایید ارسال شد."}},
        description="ارسال OTP به شماره تلفن"
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = serializer.save()
        return Response(response, status=status.HTTP_200_OK)


class GymPanelVerifyAndRegisterView(generics.GenericAPIView):
    serializer_class = GymPanelVerifyAndRegisterSerializer
    permission_classes = []  # AllowAny

    @extend_schema(
        request=GymPanelVerifyAndRegisterSerializer,
        responses={200: {"message": "ثبت‌نام و عضویت با موفقیت انجام شد."}},
        description="تأیید OTP و ایجاد یوزر + کاستومر + عضویت"
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = serializer.save()
        return Response(response, status=status.HTTP_200_OK)


# <=================== Admin Views ===================>
class AdminPanelCustomerListView(generics.ListAPIView):
    queryset = Customer.objects.all()
    serializer_class = GymPanelCustomerListSerializer
    permission_classes = [IsPlatformAdmin]


class AdminPanelCustomerDetailView(generics.RetrieveDestroyAPIView):
    """
    نمایش جزئیات کامل مشتری شامل اطلاعات کاربری،
    اشتراک‌ها، ورود و خروج‌ها، باشگاه‌های بلاک‌شده و امتیازات
    """
    queryset = Customer.objects.select_related('user').prefetch_related(
        'memberships__gym', 'inouts__gym', 'blocked_gyms__gym', 'rates__gym'
    )
    serializer_class = AdminPanelCustomerDetailSerializer
    permission_classes = [IsPlatformAdmin]


class AdminPanelCreateCustomerView(generics.GenericAPIView):
    serializer_class = AdminPanelCustomerCreateSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        return Response(
            {
                "message": "کاربر و مشتری با موفقیت ایجاد شدند.",
                "customer_id": customer.id,
                "user_phone": customer.user.phone,
                "user_full_name": customer.user.full_name,
            },
            status=status.HTTP_201_CREATED

        )
