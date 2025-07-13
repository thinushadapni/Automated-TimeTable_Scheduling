"""
URL configuration for timetable_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.urls import path
from timetable_app import views  
from timetable_app.ga import run_ga_logic

urlpatterns = [
    path("", views.login_view, name="login"),
    
    path('dashboard/', views.dashboard, name='dashboard'),
    
    path('upload-faculty/', views.upload_faculty, name='upload_faculty'),
    path('upload-course/', views.upload_course, name='upload_course'),
    path('upload-student/', views.upload_student, name='upload_student'),
    path('upload-registration/', views.upload_registration, name='upload_registration'),
    
    path('select_year_semester/', views.select_year_semester, name='select_year_semester'),
    path('add_timetable/', views.add_timetable, name='add_timetable'),
    path('view-timetable/', views.view_timetable, name='view_timetable'),
    path('download-timetable/', views.download_timetable, name='download_timetable'),
    
    path('add-class/', views.add_class, name='add_class'),
    path('run_ga_logic/', run_ga_logic, name='run_ga_logic'),
    path('run_genetic_algorithm/', views.run_genetic_algorithm, name='run_genetic_algorithm'),
]
