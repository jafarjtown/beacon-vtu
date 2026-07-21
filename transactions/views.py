from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from .models import Transaction

@login_required
def history_view(request):
    transactions = Transaction.objects.filter(user=request.user)
    
    # Filtering
    status = request.GET.get('status')
    service = request.GET.get('service')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if status:
        transactions = transactions.filter(status=status)
    if service:
        transactions = transactions.filter(transaction_type=service)
    if date_from:
        transactions = transactions.filter(created_at__date__gte=date_from)
    if date_to:
        transactions = transactions.filter(created_at__date__lte=date_to)
    
    paginator = Paginator(transactions, 20)
    page = request.GET.get('page')
    transactions = paginator.get_page(page)
    
    context = {
        'transactions': transactions,
        'status_choices': Transaction.STATUS_CHOICES,
        'type_choices': Transaction.TYPE_CHOICES,
    }
    return render(request, 'transactions/history.html', context)
