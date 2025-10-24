from django.utils import timezone
from communications.models import Notification
from gyms.models import MemberShip, Gym, GymSecretary, InOut
from accounts.models import Customer, PlatformManager, GymManager
from communications.models import Announcement, Ticket


# -------------------------------
# CUSTOMER NOTIFICATIONS
# -------------------------------

def notify_membership_expiring():
    """نوتیف برای مشتری وقتی ممبرشیپ کمتر از 5 روز یا 5 جلسه مونده"""
    today = timezone.now().date()
    memberships = MemberShip.objects.filter(is_active=True)

    for m in memberships:
        days_left = (m.validity_date - today).days if m.validity_date else None
        if (days_left is not None and days_left <= 5) or m.session_left <= 5:
            message = f"تعداد {m.session_left} جلسه یا {days_left} روز از اشتراک شما در باشگاه {m.gym.title} باقی مانده است. لطفاً تمدید کنید."
            if not Notification.objects.filter(user=m.customer.user, message=message).exists():
                Notification.objects.create(user=m.customer.user, message=message, sms=True)
                # TODO: ارسال SMS
                print(f"SMS sent to {m.customer.user.phone} for membership expiring")


def notify_new_announcement_for_customer():
    """نوتیف برای مشتری وقتی اطلاعیه جدید ثبت میشه"""
    announcements = Announcement.objects.filter(is_notified=False)
    for ann in announcements:
        # تعیین مشتریان هدف بسته به تایپ اطلاعیه
        if ann.type in ['platform_all', 'platform_customer']:
            customers = Customer.objects.all()
        elif ann.type == 'gym' and ann.gym:
            customers = Customer.objects.filter(memberships__gym=ann.gym, memberships__is_active=True)
        else:
            continue

        for c in customers:
            message = f"اطلاعیه جدید: {ann.message}"
            if not Notification.objects.filter(user=c.user, message=message).exists():
                Notification.objects.create(user=c.user, message=message, sms=ann.type == 'gym')
                if ann.type == 'gym':
                    print(f"SMS sent to {c.user.phone} for new gym announcement")
        ann.is_notified = True
        ann.save()


def notify_ticket_reply_for_customer():
    """نوتیف برای مشتری وقتی ریپلای توی تیکتی که خودش ثبت کرده باشه"""
    tickets = Ticket.objects.filter(replied_to__isnull=False)
    for t in tickets:
        customer_user = t.replied_to.sender
        message = f"تیکت شما پاسخ داده شد: {t.message}"
        if not Notification.objects.filter(user=customer_user, message=message).exists():
            Notification.objects.create(user=customer_user, message=message, sms=False)


# -------------------------------
# PLATFORM MANAGER NOTIFICATIONS
# -------------------------------

def notify_new_gym_for_platform_manager():
    """نوتیف برای پلتفرم منیجر وقتی باشگاه جدید ثبت میشه"""
    gyms = Gym.objects.filter(is_notified_to_platform=False)
    for g in gyms:
        managers = PlatformManager.objects.all()
        for pm in managers:
            message = f"باشگاه جدید ثبت شد: {g.title}"
            if not Notification.objects.filter(user=pm.user, message=message).exists():
                Notification.objects.create(user=pm.user, message=message, sms=False)
        g.is_notified_to_platform = True
        g.save()


def notify_new_ticket_for_platform_manager():
    """نوتیف برای پلتفرم منیجر وقتی تیکت جدید ثبت شده باشه (ریپلای نداره)"""
    tickets = Ticket.objects.filter(replied_to__isnull=True)
    managers = PlatformManager.objects.all()
    for t in tickets:
        message = f"تیکت جدید ثبت شد: {t.message}"
        for pm in managers:
            if not Notification.objects.filter(user=pm.user, message=message).exists():
                Notification.objects.create(user=pm.user, message=message, sms=False)


# -------------------------------
# GYM MANAGER NOTIFICATIONS
# -------------------------------

def notify_new_platform_announcement_for_gym_manager():
    """نوتیف برای مدیر باشگاه وقتی اطلاعیه تایپ platform_gym ثبت شد"""
    announcements = Announcement.objects.filter(type='platform_gym', is_notified=False)
    for ann in announcements:
        managers = GymManager.objects.filter(gym__id=ann.gym.id)
        for gm in managers:
            message = f"اطلاعیه جدید برای باشگاه شما: {ann.message}"
            if not Notification.objects.filter(user=gm.user, message=message).exists():
                Notification.objects.create(user=gm.user, message=message, sms=True)
        ann.is_notified = True
        ann.save()


def notify_ticket_reply_for_gym_manager():
    """نوتیف برای مدیر باشگاه وقتی تیکت ثبتیش پاسخ داده شد"""
    tickets = Ticket.objects.filter(replied_to__isnull=False)
    for t in tickets:
        gm_users = GymManager.objects.filter(gym__in=t.sender.gym_manager.gyms.all())
        message = f"تیکت پاسخ داده شد: {t.message}"
        for gm in gm_users:
            if not Notification.objects.filter(user=gm.user, message=message).exists():
                Notification.objects.create(user=gm.user, message=message, sms=False)


def notify_inout_for_gym_manager():
    """نوتیف برای مدیر باشگاه وقتی درخواست ورود ثبت شد"""
    inouts = InOut.objects.filter(confirm_in=False, is_notified=False)
    for io in inouts:
        gm_users = GymManager.objects.filter(gym=io.gym)
        message = f"درخواست ورود جدید ثبت شد برای مشتری {io.customer.user.full_name}"
        for gm in gm_users:
            if not Notification.objects.filter(user=gm.user, message=message).exists():
                Notification.objects.create(user=gm.user, message=message, sms=False)
        io.is_notified = True
        io.save()


def notify_new_membership_for_gym_manager():
    """نوتیف برای مدیر باشگاه وقتی ممبرشیپ جدید ایجاد شد"""
    memberships = MemberShip.objects.filter(is_notified=False)
    for m in memberships:
        gm_users = GymManager.objects.filter(gym=m.gym)
        message = f"ممبرشیپ جدید برای مشتری {m.customer.user.full_name} در باشگاه {m.gym.title} ایجاد شد"
        for gm in gm_users:
            if not Notification.objects.filter(user=gm.user, message=message).exists():
                Notification.objects.create(user=gm.user, message=message, sms=False)
        m.is_notified = True
        m.save()


# -------------------------------
# GYM SECRETARY NOTIFICATIONS
# -------------------------------

def notify_secretary_notifications():
    """تمام نوتیف های مدیر باشگاه برای منشی"""
    secretaries = GymSecretary.objects.all()
    for sec in secretaries:
        gm_notifications = Notification.objects.filter(user=sec.gym.manager.user)  # فرض کنیم user مدیر باشگاهه
        for n in gm_notifications:
            message = f"{n.message}"  # میخوای متن همون باشه
            if not Notification.objects.filter(user=sec.user, message=message).exists():
                Notification.objects.create(user=sec.user, message=message, sms=n.sms)
