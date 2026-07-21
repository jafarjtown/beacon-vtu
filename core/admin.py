from django.contrib import admin
from .models import SiteSettings, Announcement, SupportTicket, TicketReply


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ['site_name', 'maintenance_mode', 'updated_at']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ['title', 'is_active', 'priority', 'start_date', 'end_date']
    list_filter = ['is_active', 'priority']
    search_fields = ['title', 'content']
    date_hierarchy = 'created_at'


class TicketReplyInline(admin.TabularInline):
    model = TicketReply
    extra = 0
    readonly_fields = ['created_at']


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ['ticket_id', 'user', 'subject', 'status', 'priority', 'created_at']
    list_filter = ['status', 'priority', 'created_at']
    search_fields = ['ticket_id', 'subject', 'user__email']
    inlines = [TicketReplyInline]
    date_hierarchy = 'created_at'

