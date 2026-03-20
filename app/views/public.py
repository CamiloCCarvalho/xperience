from django.shortcuts import render
from app.content.home import data_page

url_public = "xperience/pages/public/"

# public routes
def home(request):
    return render(
        request,
        url_public + "home.html",
        context=data_page
    )

def plataform(request):
    return render(request, url_public + "plataform.html")

def solution(request):
    return render(request, url_public + "solutions.html")

def resources(request):
    return render(request, url_public + "resources.html")

def prices(request):
    return render(request, url_public + "prices.html")

def contact(request):
    return render(request, url_public + "contact.html")

def about(request):
    return render(request, url_public + "about.html")