import requests, uuid
from datetime import datetime
from django.conf import settings
from django.http import JsonResponse
from services.models import ApiProviderResponse, ServiceProvider


BASE_URL =  "https://sandbox.vtpass.com/api"
API_KEY = "d7660ea78c6658d08f338999f78ccda6"

def generate_request_id():
    # First 12 characters must be YYYYMMDDHHMM
    return datetime.now().strftime("%Y%m%d%H%M") + uuid.uuid4().hex[:10]


def data_plans(request):
    service_id = request.GET.get("serviceID", "mtn-data")
    provider = ServiceProvider.objects.get(api_id=service_id)

    api_response, created = ApiProviderResponse.objects.get_or_create(
      provider=provider,
            defaults={
                "data": dict(),
            }
        )
    if created:
      headers = {
          "api-key": settings.VTPASS_API_KEY,
          "secret-key": settings.VTPASS_SECRET_KEY,
      }
  
      response = requests.get(
          settings.VTPASS_VARIATIONS_URL,
          params={"serviceID": service_id},
          headers=headers
      )
      api_response.data = response.json()
      api_response.save()
    data = api_response.data.get("content")
    print(data)
    return JsonResponse(data)

def _request(endpoint, payload):
    """
    Send a request to VTpass.
    """

    headers = {
        "api-key": API_KEY,
        "secret-key": settings.VTPASS_SECRET_KEY,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            f"{BASE_URL}/{endpoint.lstrip('/')}",
            json=payload,
            headers=headers,
            timeout=30,
        )

        response.raise_for_status()
        data = response.json()
        
        return {
            "success": data.get("code") == "000" or data.get("response_description") == "TRANSACTION SUCCESSFUL",
            "message": data.get("response_description")
                       or data.get("response_message")
                       or data.get("message", ""),
            "reference": (
                data.get("content", {}).get("transactions", {}).get("transactionId")
                or data.get("requestId")
            ),
            "data": data,
        }

    except requests.HTTPError:
        return {
            "success": False,
            "message": f"HTTP {response.status_code}: {response.text}",
            "reference": None,
            "data": None,
        }

    except requests.RequestException as e:
        return {
            "success": False,
            "message": str(e),
            "reference": None,
            "data": None,
        }

def buy_data_api(network, plan, phone):
    #return {'success': True, "reference": f"REF{uuid.uuid4().hex[:12].upper()}"}
    request_id = generate_request_id()
    
    payload = {
        "request_id": request_id,
        "serviceID": plan.get("serviceID"),        # e.g. "mtn-data"
        "billersCode": phone,
        "variation_code": plan.get("variation_code"),
        "phone": phone,
        # Optional
        #"amount": plan.get("variation_amount"),
    }
    

    return _request("pay", payload)

def buy_airtime_api(network, phone, amount):
    #return {'success': True, "reference": f"REF{uuid.uuid4().hex[:12].upper()}"}
    request_id = generate_request_id()
    
    payload = {
        "request_id": request_id,
        "serviceID": network,
        "phone": phone,
        "amount": amount,
    }

    return _request("pay", payload)