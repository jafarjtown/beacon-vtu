
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import SiteSettings, Announcement


def landing_page(request):
    """Premium landing page with all sections"""
    settings = SiteSettings.load()
    announcements = Announcement.objects.filter(is_active=True)[:3]
    
    context = {
        'settings': settings,
        'announcements': announcements,
        'features': [
            {
                'icon': 'fa-bolt',
                'title': 'Instant Delivery',
                'description': 'All purchases are processed instantly with real-time confirmation.'
            },
            {
                'icon': 'fa-shield-halved',
                'title': 'Bank-Grade Security',
                'description': 'Your data and transactions are protected with enterprise-level encryption.'
            },
            {
                'icon': 'fa-mobile-screen',
                'title': 'All Networks',
                'description': 'Support for MTN, Airtel, Glo, 9mobile, and all major service providers.'
            },
            {
                'icon': 'fa-wallet',
                'title': 'Smart Wallet',
                'description': 'Fund your wallet once and make multiple purchases seamlessly.'
            },
            {
                'icon': 'fa-share-nodes',
                'title': 'Share & Gift',
                'description': 'Generate unique links to share airtime and data with anyone.'
            },
            {
                'icon': 'fa-headset',
                'title': '24/7 Support',
                'description': 'Our dedicated team is always available to assist you.'
            },
        ],
        'services': [
            {'icon': 'fa-signal', 'name': 'Airtime', 'description': 'Recharge any network instantly'},
            {'icon': 'fa-wifi', 'name': 'Data Bundles', 'description': 'Affordable data plans for all networks'},
            {'icon': 'fa-bolt', 'name': 'Electricity', 'description': 'Pay electricity bills nationwide'},
            {'icon': 'fa-tv', 'name': 'Cable TV', 'description': 'DSTV, GOTV, Startimes subscriptions'},
            {'icon': 'fa-globe', 'name': 'Internet', 'description': 'Broadband and ISP subscriptions'},
            {'icon': 'fa-graduation-cap', 'name': 'Exam Pins', 'description': 'WAEC, NECO, JAMB pins'},
        ],
        'testimonials': [
            {
                'name': 'Chinedu Okafor',
                'role': 'Business Owner',
                'text': 'VTU Pro has transformed how I manage airtime for my team. The sharing feature is genius!',
                'rating': 5
            },
            {
                'name': 'Amina Bello',
                'role': 'Student',
                'text': 'Fast, reliable, and the wallet system makes budgeting so much easier. Highly recommended!',
                'rating': 5
            },
            {
                'name': 'Emmanuel Adeyemi',
                'role': 'Developer',
                'text': 'The API-ready architecture gives me confidence to build integrations. Clean codebase.',
                'rating': 5
            },
        ],
        'faqs': [
            {
                'question': 'How do I fund my wallet?',
                'answer': 'Navigate to the Wallet page, select Bank Transfer, and transfer to the provided account details. Click Confirm Payment to credit your wallet instantly.'
            },
            {
                'question': 'Is my money safe?',
                'answer': 'Absolutely. We use bank-grade encryption, secure sessions, and all transactions are logged with complete audit trails.'
            },
            {
                'question': 'Can I share airtime with friends?',
                'answer': 'Yes! Use our Claim Link feature to generate a unique URL. Share it with anyone, and they can claim the airtime without creating an account.'
            },
            {
                'question': 'What happens if a transaction fails?',
                'answer': 'Failed transactions are automatically reversed to your wallet within minutes. You can also contact our 24/7 support team.'
            },
            {
                'question': 'Do you support bulk purchases?',
                'answer': 'Yes, you can purchase multiple units and share them via claim links. Each slot can be claimed individually.'
            },
        ],
    }
    return render(request, 'core/landing.html', context)


def custom_404(request, exception=None):
    """Custom 404 error page"""
    return render(request, '404.html', status=404)


def custom_500(request):
    """Custom 500 error page"""
    return render(request, '500.html', status=500)


@require_http_methods(["POST"])
def toggle_theme(request):
    """Toggle between light and dark mode"""
    current_theme = request.session.get('theme', 'light')
    new_theme = 'dark' if current_theme == 'light' else 'light'
    request.session['theme'] = new_theme
    return JsonResponse({'theme': new_theme})


