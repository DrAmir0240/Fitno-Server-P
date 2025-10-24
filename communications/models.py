from django.db import models
from django.utils import timezone

from accounts.models import User
from gyms.models import Gym


# Create your models here.
class Ticket(models.Model):
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_tickets')
    message = models.TextField()
    send_time = models.DateTimeField(auto_now_add=True)
    replied_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')

    def __str__(self):
        return f"Ticket {self.id} from {self.sender}"


class Notification(models.Model):
    message = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    is_read = models.BooleanField(default=False)
    sms = models.BooleanField(default=False)
    sent_sms = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    # customer : Announcement tickets In/Out DiscountCode
    # gym : Announcement tickets transactions In/Out MemberShip
    # admin : Gym Ticket

    def __str__(self):
        return f"Notification for {self.user}"


class Announcement(models.Model):
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='announcements')
    gym = models.ForeignKey(Gym, on_delete=models.SET_NULL, null=True, blank=True, related_name='announcements')
    type = models.CharField(max_length=100, choices=(
        ('gym', 'باشگاهی'),
        ('platform_all', 'پلتفرم به همه'),
        ('platform_gym', 'پلتفرم به باشگاه'),
        ('platform_customer', 'پلتفرم به کاربر')
    ), default='gym')
    message = models.TextField()

    def __str__(self):
        return f"Announcement {self.gym.title} from {self.sender.gym_manager.user.full_name}"
