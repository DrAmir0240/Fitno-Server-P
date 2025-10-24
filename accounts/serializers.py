import secrets
from datetime import timedelta

from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import Customer, User, GymManager, OTP
from gyms.models import Gym, MemberShip, InOut, BlockList, Rate, MemberShipType


# <=================== User Views ===================>
class UserRoleStatusSerializer(serializers.Serializer):
    is_authenticated = serializers.BooleanField()
    name = serializers.CharField(allow_null=True)
    is_customer = serializers.BooleanField()
    is_gym_manager = serializers.BooleanField()
    is_platform_manager = serializers.BooleanField()
    phone_number = serializers.CharField(allow_null=True)


class PasswordLoginSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=11)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        phone = attrs.get("phone")
        password = attrs.get("password")

        user = authenticate(phone=phone, password=password)
        if not user:
            raise serializers.ValidationError("شماره یا پسورد اشتباه است.")

        if not hasattr(user, "customer"):
            raise serializers.ValidationError("این کاربر مشتری نیست.")

        attrs["user"] = user
        return attrs


class RequestOTPSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=15, help_text="شماره موبایل (مثال: 09123456789)")


class RequestOTPResponseSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=100, help_text="پیام موفقیت یا خطا")
    error = serializers.CharField(max_length=100, required=False, help_text="پیام خطا (در صورت وجود)")


class VerifyOTPSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=15, help_text="شماره موبایل (مثال: 09123456789)")
    code = serializers.CharField(max_length=8, help_text="کد OTP (مثال: 12345678)")


class VerifyOTPResponseSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=100, help_text="پیام موفقیت یا خطا")
    error = serializers.CharField(max_length=100, required=False, help_text="پیام خطا (در صورت وجود)")


class RequestOTPAuthenticatedSerializer(serializers.Serializer):
    """
    Serializer خالی — چون شماره از request.user گرفته می‌شود.
    فقط برای سازگاری با GenericAPIView و مستندات استفاده می‌شود.
    """
    pass


class ResetPasswordWithOTPSerializer(serializers.Serializer):
    otp_code = serializers.CharField(max_length=5)
    new_password = serializers.CharField(write_only=True, min_length=6)

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if user is None or not user.is_authenticated:
            raise serializers.ValidationError({"detail": "کاربر احراز هویت نشده است"})

        if not getattr(user, "phone", None):
            raise serializers.ValidationError({"detail": "شماره تلفن برای این کاربر ثبت نشده است"})

        otp_code = attrs.get("otp_code")
        otp = OTP.objects.filter(user=user, code=otp_code).order_by('-created_at').first()
        if not otp:
            raise serializers.ValidationError({"otp_code": "کد وارد شده معتبر نیست"})

        if not otp.is_valid():
            raise serializers.ValidationError({"otp_code": "کد منقضی شده است"})

        attrs["user"] = user
        attrs["otp"] = otp
        return attrs

    def save(self):
        user = self.validated_data["user"]
        otp = self.validated_data["otp"]
        new_password = self.validated_data["new_password"]

        user.set_password(new_password)
        user.save()

        # حذف OTP بعد از استفاده
        otp.delete()

        return user


# <=================== Customer Views ===================>
class CustomerRegisterSerializer(serializers.ModelSerializer):
    # فیلدهای یوزر
    phone = serializers.CharField(max_length=11, write_only=True)
    full_name = serializers.CharField(max_length=255, write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True, write_only=True)
    password = serializers.CharField(write_only=True, min_length=6)

    # فیلدهای مشتری
    national_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    city = serializers.CharField(max_length=255, write_only=True)
    profile_photo = serializers.ImageField(required=False, allow_null=True)
    gender = serializers.ChoiceField(choices=(('male', 'مرد'), ('female', 'زن')), default='male')

    # توکن‌ها
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)

    class Meta:
        model = Customer
        fields = [
            'phone', 'full_name', 'email', 'password',
            'national_code', 'city', 'profile_photo', 'gender',
            'access', 'refresh'
        ]

    def create(self, validated_data):
        phone = validated_data.pop('phone')
        full_name = validated_data.pop('full_name')
        email = validated_data.pop('email', None)
        password = validated_data.pop('password')
        national_code = validated_data.pop('national_code', None)
        city = validated_data.pop('city')
        profile_photo = validated_data.pop('profile_photo', None)
        gender = validated_data.pop('gender', 'male')

        # ساخت یوزر
        user = User.objects.create(
            phone=phone,
            full_name=full_name,
            email=email
        )
        user.set_password(password)
        user.save()

        # ساخت مشتری
        customer = Customer.objects.create(
            user=user,
            national_code=national_code,
            city=city,
            profile_photo=profile_photo,
            gender=gender
        )
        return customer

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # اطلاعات یوزر
        data['user_id'] = instance.user.id
        data['phone'] = instance.user.phone
        data['full_name'] = instance.user.full_name
        data['email'] = instance.user.email

        # اطلاعات مشتری
        data['national_code'] = instance.national_code
        data['city'] = instance.city
        data['gender'] = instance.gender
        data['profile_photo'] = instance.profile_photo.url if instance.profile_photo else None

        # توکن‌ها
        refresh = RefreshToken.for_user(instance.user)
        data['refresh'] = str(refresh)
        data['access'] = str(refresh.access_token)

        return data


class CustomerProfileSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(source="user.phone", read_only=True)  # غیرقابل تغییر
    email = serializers.EmailField(source="user.email", read_only=True)  # غیرقابل تغییر
    full_name = serializers.CharField(source="user.full_name", required=False)

    class Meta:
        model = Customer
        fields = [
            'id', 'phone', 'email', 'full_name',
            'national_code', 'city', 'gender', 'profile_photo'
        ]

    def update(self, instance, validated_data):
        # آپدیت Customer
        instance.national_code = validated_data.get("national_code", instance.national_code)
        instance.city = validated_data.get("city", instance.city)
        instance.gender = validated_data.get("gender", instance.gender)

        if "profile_photo" in validated_data:
            instance.profile_photo = validated_data.get("profile_photo", instance.profile_photo)

        instance.save()

        # آپدیت full_name در User (اجازه داریم تغییر بدیم)
        user_data = validated_data.get("user", {})
        if "full_name" in user_data:
            instance.user.full_name = user_data["full_name"]
            instance.user.save()

        return instance


# <=================== Gym Views ===================>
class GymManagerSerializer(serializers.ModelSerializer):
    class Meta:
        model = GymManager
        fields = ['id', 'national_code', 'verification_code', 'city', 'invitation_code']
        read_only_fields = ['id', ]

    def create(self, validated_data):
        # یوزر از کانتکست گرفته میشه
        user = self.context['request'].user
        return GymManager.objects.create(user=user, **validated_data)


class GymSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gym
        fields = [
            'id', 'title', 'location', 'address', 'main_img',
            'phone', 'headline_phone', 'commission_type',
            'facilities', 'description', 'work_hours_per_day', 'work_days_per_week'
        ]
        read_only_fields = ['id', 'manager']

    def create(self, validated_data):
        # مدیر از یوزر لاگین گرفته میشه
        user = self.context['request'].user
        gym_manager = getattr(user, 'gym_manager', None)
        if not gym_manager:
            raise serializers.ValidationError("این کاربر مدیر باشگاه نیست.")
        return Gym.objects.create(manager=gym_manager, **validated_data)


class GymPanelCustomerListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='user.full_name')
    phone = serializers.CharField(source='user.phone')
    email = serializers.EmailField(source='user.email')
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            'id',
            'full_name',
            'phone',
            'is_active',
            'email',
            'profile_photo',
            'national_code',
            'city',
            'gender',
        ]

    def get_is_active(self, obj):
        """بررسی فعال بودن ممبرشیپ مشتری در باشگاه‌های متعلق به منشی یا مدیر"""
        user = self.context['request'].user
        today = timezone.now().date()

        # 🎯 استخراج باشگاه‌هایی که این کاربر (مدیر یا منشی) در آنها فعاله
        related_gyms = Gym.objects.none()

        # اگه مدیر باشگاهه
        if hasattr(user, 'gym_manager'):
            related_gyms = Gym.objects.filter(manager=user.gym_manager)

        # اگه منشی باشگاهه
        elif hasattr(user, 'gym_secretary'):
            related_gyms = Gym.objects.filter(id=user.gym_secretary.gym.id)

        # بررسی ممبرشیپ‌های معتبر مرتبط با اون باشگاه‌ها
        active_memberships = obj.memberships.filter(
            gym__in=related_gyms,
            validity_date__gte=today,  # تاریخ هنوز تموم نشده
            session_left__gt=0  # جلسه باقی مونده
        )

        return active_memberships.exists()


class GymPanelCustomerMemberShipSerializer(serializers.ModelSerializer):
    gym_title = serializers.CharField(source='gym.title', read_only=True)
    type_title = serializers.CharField(source='type.title', read_only=True)

    class Meta:
        model = MemberShip
        fields = ['id', 'gym_title', 'type_title', 'start_date', 'validity_date', 'is_active']


class GymPanelCustomerInOutSerializer(serializers.ModelSerializer):
    gym_title = serializers.CharField(source='gym.title', read_only=True)

    class Meta:
        model = InOut
        fields = ['id', 'gym_title', 'enter_time', 'out_time', 'confirm_in']


class GymPanelCustomerDetailSerializer(serializers.ModelSerializer):
    memberships = GymPanelCustomerMemberShipSerializer(many=True, read_only=True)
    full_name = serializers.CharField(source='user.full_name')
    inouts = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            'id',
            'user',
            'full_name',
            'profile_photo',
            'national_code',
            'city',
            'gender',
            'balance',
            'is_active',
            'memberships',
            'inouts',
        ]

    def get_is_active(self, obj):
        """بررسی فعال بودن ممبرشیپ مشتری در باشگاه‌های متعلق به منشی یا مدیر"""
        user = self.context['request'].user
        today = timezone.now().date()

        # استخراج باشگاه‌های مرتبط با کاربر جاری
        related_gyms = Gym.objects.none()
        if hasattr(user, 'gym_manager'):
            related_gyms = Gym.objects.filter(manager=user.gym_manager)
        elif hasattr(user, 'gym_secretary'):
            related_gyms = Gym.objects.filter(id=user.gym_secretary.gym.id)

        # بررسی ممبرشیپ‌های معتبر در همین باشگاه‌ها
        active_memberships = obj.memberships.filter(
            gym__in=related_gyms,
            validity_date__gte=today,
            session_left__gt=0
        )
        return active_memberships.exists()

    def get_inouts(self, obj):
        """فقط ورود/خروج‌های مربوط به باشگاه‌های مدیر یا منشی"""
        user = self.context['request'].user

        related_gyms = Gym.objects.none()
        if hasattr(user, 'gym_manager'):
            related_gyms = Gym.objects.filter(manager=user.gym_manager)
        elif hasattr(user, 'gym_secretary'):
            related_gyms = Gym.objects.filter(id=user.gym_secretary.gym.id)

        inouts = obj.inouts.filter(gym__in=related_gyms).order_by('-enter_time')
        return GymPanelCustomerInOutSerializer(inouts, many=True).data


class GymPanelCustomerChoicesSerializer(serializers.ModelSerializer):
    gym_title = serializers.CharField(source='gyms.title', read_only=True)

    class Meta:
        model = MemberShipType
        fields = ['id', 'title', 'gym_title', 'days', 'type', 'price', 'description']


class GymPanelRequestOTPForCustomerSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=11)

    def validate_phone(self, phone):
        if not phone.startswith("09") or len(phone) != 11:
            raise serializers.ValidationError("شماره موبایل معتبر نیست.")
        return phone

    def create(self, validated_data):
        phone = validated_data["phone"]

        # بررسی وجود یوزر (اگر نبود، موقت بسازیم)
        user, created = User.objects.get_or_create(phone=phone, defaults={"full_name": "کاربر جدید"})

        # حذف OTPهای قبلی
        OTP.objects.filter(user=user).delete()

        # تولید کد جدید
        otp_code = str(secrets.randbelow(100000)).zfill(5)
        expires_at = timezone.now() + timedelta(minutes=2)
        otp = OTP.objects.create(user=user, code=otp_code, expires_at=expires_at)

        otp.send_otp(phone=phone, otp_code=otp_code)
        return {"message": "کد تایید ارسال شد."}


class GymPanelVerifyAndRegisterSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=11)
    otp_code = serializers.CharField(max_length=5)
    full_name = serializers.CharField(max_length=255)
    profile_photo = serializers.ImageField(required=False)
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    city = serializers.CharField(max_length=255, required=False, allow_blank=True)
    gender = serializers.ChoiceField(choices=(('male', 'مرد'), ('female', 'زن')), default='male')
    national_code = serializers.CharField(required=False, allow_blank=True)
    membership_type_id = serializers.IntegerField()

    def validate(self, attrs):
        phone = attrs.get("phone")
        otp_code = attrs.get("otp_code")

        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            raise serializers.ValidationError({"phone": "یوزری با این شماره پیدا نشد."})

        otp = OTP.objects.filter(user=user, code=otp_code).order_by('-created_at').first()
        if not otp or not otp.is_valid():
            raise serializers.ValidationError({"otp_code": "کد وارد شده معتبر یا منقضی شده است."})

        # بررسی عضویت
        try:
            membership_type = MemberShipType.objects.get(id=attrs["membership_type_id"])
        except MemberShipType.DoesNotExist:
            raise serializers.ValidationError({"membership_type_id": "نوع عضویت یافت نشد."})

        attrs["user"] = user
        attrs["membership_type"] = membership_type
        return attrs

    def create(self, validated_data):
        user = validated_data["user"]
        otp = OTP.objects.filter(user=user).last()
        otp.delete()

        # آپدیت اطلاعات کاربر
        user.full_name = validated_data["full_name"]
        user.email = validated_data.get("email")
        user.is_active = True
        user.save()

        # ایجاد یا گرفتن Customer
        customer, _ = Customer.objects.get_or_create(user=user)
        customer.profile_photo = validated_data.get("profile_photo")
        customer.gender = validated_data.get("gender")
        customer.city = validated_data.get("city")
        customer.national_code = validated_data.get("national_code")
        customer.save()

        # ایجاد Membership
        membership_type = validated_data["membership_type"]
        MemberShip.objects.create(
            customer=customer,
            gym=membership_type.gyms,
            type=membership_type,
            start_date=timezone.now().date(),
            validity_date=timezone.now().date() + timedelta(days=membership_type.days),
            session_left=membership_type.days,
            price=membership_type.price,
            is_active=True
        )

        return {"message": "ثبت‌نام و عضویت با موفقیت انجام شد."}


# <=================== Admin Views ===================>
class AdminPanelCustomerListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='user.full_name')
    phone = serializers.CharField(source='user.phone')
    email = serializers.EmailField(source='user.email')
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            'id',
            'full_name',
            'phone',
            'is_active',
            'email',
            'balance',
            'profile_photo',
            'national_code',
            'city',
            'gender',
        ]

    def get_is_active(self, obj):
        """اگر حداقل یکی از ممبرشیپ‌ها هنوز منقضی نشده و جلسه باقی دارد → True"""
        today = timezone.now().date()
        active_memberships = obj.memberships.filter(
            validity_date__gte=today,  # هنوز منقضی نشده
            session_left__gt=0  # جلسه باقی مانده دارد
        )
        return active_memberships.exists()


class AdminPanelCustomerMembershipSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source='type.title')
    gym = serializers.CharField(source='gym.title')

    class Meta:
        model = MemberShip
        fields = ['title', 'gym', 'start_date', 'validity_date']


class AdminPanelCustomerInOutSerializer(serializers.ModelSerializer):
    gym = serializers.CharField(source='gym.title')

    class Meta:
        model = InOut
        fields = ['gym', 'enter_time', 'out_time']


class AdminPanelCustomerBlockListSerializer(serializers.ModelSerializer):
    gym = serializers.CharField(source='gym.title')

    class Meta:
        model = BlockList
        fields = ['gym', 'description']


class AdminPanelCustomerRateSerializer(serializers.ModelSerializer):
    gym = serializers.CharField(source='gym.title')

    class Meta:
        model = Rate
        fields = ['gym', 'rate']


class AdminPanelCustomerDetailSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='user.full_name')
    phone = serializers.CharField(source='user.phone')
    is_active = serializers.SerializerMethodField()
    memberships = AdminPanelCustomerMembershipSerializer(many=True, read_only=True)
    inouts = AdminPanelCustomerInOutSerializer(many=True, read_only=True)
    blocked_gyms = AdminPanelCustomerBlockListSerializer(many=True, read_only=True)
    rates = AdminPanelCustomerRateSerializer(many=True, read_only=True)

    class Meta:
        model = Customer
        fields = [
            'id', 'full_name', 'phone', 'is_active', 'city', 'gender', 'balance', 'profile_photo',
            'memberships', 'inouts', 'blocked_gyms', 'rates'
        ]

    def get_is_active(self, obj):
        """اگر حداقل یکی از ممبرشیپ‌ها هنوز منقضی نشده و جلسه باقی دارد → True"""
        today = timezone.now().date()
        active_memberships = obj.memberships.filter(
            validity_date__gte=today,  # هنوز منقضی نشده
            session_left__gt=0  # جلسه باقی مانده دارد
        )
        return active_memberships.exists()

    def destroy(self, instance):
        instance.is_deleted = True
        instance.save()
        return instance


class AdminPanelCustomerCreateSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=11)
    full_name = serializers.CharField(max_length=255)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    city = serializers.CharField(required=False, allow_blank=True)
    gender = serializers.ChoiceField(choices=(('male', 'مرد'), ('female', 'زن')), default='male')
    national_code = serializers.CharField(required=False, allow_blank=True)
    profile_photo = serializers.ImageField(required=False, allow_null=True)

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("کاربری با این شماره تلفن وجود دارد.")
        return value

    def create(self, validated_data):
        # داده‌های کاربر و مشتری را از validated_data جدا می‌کنیم
        phone = validated_data.get('phone')
        full_name = validated_data.get('full_name')
        email = validated_data.get('email', None)
        gender = validated_data.get('gender', 'male')
        national_code = validated_data.get('national_code', '')
        city = validated_data.get('city', '')
        profile_photo = validated_data.get('profile_photo', None)

        # ایجاد کاربر
        user = User.objects.create(
            phone=phone,
            full_name=full_name,
            email=email,
        )

        # ایجاد مشتری مرتبط با کاربر
        customer = Customer.objects.create(
            user=user,
            gender=gender,
            national_code=national_code,
            city=city,
            profile_photo=profile_photo,
        )

        return customer
