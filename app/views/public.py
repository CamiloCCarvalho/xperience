from django.shortcuts import render
from app.content.home import data_page_home
from utils.faker import fake_user

page_public = "xperience/pages/public/"

# public routes
def home(request):
    return render(
        request,
        page_public + "home.html",
        context={
            "user_data": fake_user.make_user_data(),
            "data_page": data_page_home,
        }
        
    )

def plataform(request):
    return render(request, page_public + "plataform.html")

def solution(request):
    return render(request, page_public + "solutions.html")

def resources(request):
    return render(request, page_public + "resources.html")

def prices(request):
    return render(request, page_public + "prices.html")

def contact(request):
    return render(request, page_public + "contact.html")

def about(request):
    return render(request, page_public + "about.html")