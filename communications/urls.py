from django.urls import path
from communications import views

urlpatterns = [
    # <=================== Customer Views ===================>
    path('customer/announcements/gym/', views.CustomerPanelAnnouncementGym.as_view(),
         name='customer-gym-announcement-list'),
    path('customer/announcements/platform/', views.CustomerPanelAnnouncementPlatform.as_view(),
         name='customer-platform-announcement-list'),
    path('customer/tickets/', views.CustomerPanelTicketListCreate.as_view(),
         name='customer-tickets'),
    path('customer/notifications/', views.CustomerPanelNotificationList.as_view(),
         name='customer-notifications'),
    path('customer/notifications/unread/', views.CustomerPanelNotificationUnreadList.as_view(),
         name='customer-notifications-unread'),
    path('customer/notifications/<int:pk>', views.CustomerPanelNotificationDetail.as_view(),
         name='customer-notification-detail'),

    # <=================== Gym Views ===================>
    path('gym-panel/notifications/', views.GymPanelNotificationList.as_view(),
         name='gym-panel-notifications'),
    path('gym-panel/notifications/unread/', views.GymPanelNotificationUnreadList.as_view(),
         name='gym-panel-notifications-unread'),
    path('gym-panel/notifications/<int:pk>', views.GymPanelNotificationDetail.as_view(),
         name='gym-panel-notification-detail'),

    # <=================== Admin Views ===================>
    path('admin-panel/notifications/', views.AdminPanelNotificationList.as_view(),
         name='admin-panel-notifications'),
    path('admin-panel/notifications/unread/', views.AdminPanelNotificationUnreadList.as_view(),
         name='admin-notifications-unread'),
    path('admin-panel/notifications/<int:pk>', views.AdminPanelNotificationDetail.as_view(),
         name='admin-panel-notification-detail'),
]
