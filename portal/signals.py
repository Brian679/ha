from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Payment


@receiver(post_save, sender=Payment)
def update_invoice_after_payment(sender, instance, **kwargs):
    instance.invoice.refresh_status()


@receiver(post_delete, sender=Payment)
def update_invoice_after_payment_deletion(sender, instance, **kwargs):
    instance.invoice.refresh_status()
