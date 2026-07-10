from django.urls import path

from . import public_views as views

urlpatterns = [
    path("articles", views.PublicArticlesView.as_view(), name="public-articles"),
    path("articles/featured", views.PublicFeaturedArticlesView.as_view(), name="public-articles-featured"),
    path("articles/<slug:slug>", views.PublicArticleDetailView.as_view(), name="public-article"),
    path("theses", views.PublicThesesView.as_view(), name="public-theses"),
    path("events", views.PublicEventsView.as_view(), name="public-events"),
    path("news", views.PublicNewsView.as_view(), name="public-news"),
    path("news/<slug:slug>", views.PublicNewsDetailView.as_view(), name="public-news-detail"),
    path("pages/<slug:slug>", views.PublicPageView.as_view(), name="public-page"),
    path("faqs", views.PublicFAQsView.as_view(), name="public-faqs"),
    path("homepage", views.PublicHomepageView.as_view(), name="public-homepage"),
    path("home", views.PublicHomeDataView.as_view(), name="public-home"),
]
