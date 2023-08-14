from django.shortcuts import render, redirect

from main.models import Tour, Review
from concurrent.futures import ThreadPoolExecutor
from django.http import JsonResponse
from main.serializers import MainReviewSerializer
from festival.serializers import FestivalSerializer

from main.serializers import ReviewWithTourSerializer

from member.models import CustomUser

from rest_framework import generics

from member.serializers import CustomUserSerializer

from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.decorators import login_required

from django.conf import settings
from member.models import CustomUser
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.google import views as google_view
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from django.http import JsonResponse
import requests
from rest_framework import status
from json.decoder import JSONDecodeError

# Create your views here.
class ChangeNicknameView(generics.UpdateAPIView):
    serializer_class = CustomUserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

@login_required(login_url='/member/login')
def user_like_view_logic(request):
    queryset = Tour.objects.filter(like_users=request.user)
    serializer = FestivalSerializer(queryset, many=True)
    return serializer.data

@login_required(login_url='/member/login')
def user_review_logic(request):
    queryset = Review.objects.filter(user=request.user)
    serializer = ReviewWithTourSerializer(queryset, many=True)
    return serializer.data


def MypageCombinedView(request):
    data = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_view1 = executor.submit(user_like_view_logic, request)
        future_view2 = executor.submit(user_review_logic, request)

        data['nickname'] = request.user.nickname
        data['user_like_response'] = future_view1.result()
        data['user_review_response'] = future_view2.result()

    return JsonResponse(data)

state = getattr(settings, 'STATE')
BASE_URL = 'http://127.0.0.1:8000/'
GOOGLE_CALLBACK_URI = BASE_URL + 'member/google/callback/'

def google_login(request):
    
    """
    Code Request
    """
    scope = "https://www.googleapis.com/auth/userinfo.email"
    client_id = getattr(settings, "SOCIAL_AUTH_GOOGLE_CLIENT_ID")
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&response_type=code&redirect_uri={GOOGLE_CALLBACK_URI}&scope={scope}")

def google_callback(request):
    client_id = getattr(settings, "SOCIAL_AUTH_GOOGLE_CLIENT_ID")
    client_secret = getattr(settings, "SOCIAL_AUTH_GOOGLE_SECRET")
    code = request.GET.get('code')
    
    """
    Access Token Request
    """
    token_req = requests.post(
        f"https://oauth2.googleapis.com/token?client_id={client_id}&client_secret={client_secret}&code={code}&grant_type=authorization_code&redirect_uri={GOOGLE_CALLBACK_URI}&state={state}")
    token_req_json = token_req.json()
    error = token_req_json.get("error")
    if error is not None:
        raise JSONDecodeError(error)
    access_token = token_req_json.get('access_token')
    
    """
    Email Request
    """
    email_req = requests.get(
        f"https://www.googleapis.com/oauth2/v1/tokeninfo?access_token={access_token}")
    email_req_status = email_req.status_code
    
    if email_req_status != 200:
        return JsonResponse({'err_msg': 'failed to get email'}, status=status.HTTP_400_BAD_REQUEST)
    email_req_json = email_req.json()
    email = email_req_json.get('email')
    
    """
    Signup or Signin Request
    """
    
    try:
        user = CustomUser.objects.get(email=email)
        # 기존에 가입된 유저의 Provider가 google이 아니면 에러 발생, 맞으면 로그인
        # 다른 SNS로 가입된 유저
        
        social_user = SocialAccount.objects.get(user=user)
        if social_user is None:
            return JsonResponse({'err_msg': 'email exists but not social user'}, status=status.HTTP_400_BAD_REQUEST)
        
        if social_user.provider != 'google':
            return JsonResponse({'err_msg': 'no matching social type'}, status=status.HTTP_400_BAD_REQUEST)
        
        # 기존에 Google로 가입된 유저
        data = {'access_token': access_token, 'code': code}
        accept = requests.post(
            f"{BASE_URL}member/google/login/finish/", data=data)
        accept_status = accept.status_code
        
        if accept_status != 200:
            return JsonResponse({'err_msg': 'failed to signin'}, status=accept_status)
        accept_json = accept.json()
        accept_json.pop('user', None)
        return JsonResponse(accept_json)
    
    except CustomUser.DoesNotExist:
        # 기존에 가입된 유저가 없으면 새로 가입
        data = {'access_token': access_token, 'code': code}
        accept = requests.post(
            f"{BASE_URL}member/google/login/finish/", data=data)
        accept_status = accept.status_code
        
        if accept_status != 200:
            return JsonResponse({'err_msg': 'failed to signup'}, status=accept_status)
        accept_json = accept.json()
        accept_json.pop('user', None)
        return JsonResponse(accept_json)

class GoogleLogin(SocialLoginView):
    adapter_class = google_view.GoogleOAuth2Adapter
    callback_url = GOOGLE_CALLBACK_URI
    client_class = OAuth2Client