from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("how-it-works/", views.how_it_works, name="how_it_works"),
    path("for-manufacturers/", views.for_manufacturers, name="for_manufacturers"),
    path("contact/", views.contact, name="contact"),
    path("pricing-fees/", views.pricing_fees, name="pricing_fees"),
    path("trust-safety/", views.trust_safety, name="trust_safety"),
    path("faq/", views.faq, name="faq"),
    path("grievance-redressal/", views.grievance_redressal, name="grievance_redressal"),
    path("help/", views.help_page, name="help_page"),
    path("sitemap.xml", views.sitemap_xml, name="sitemap_xml"),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path("privacy/", views.privacy_policy, name="privacy_policy"),
    path("terms/", views.terms, name="terms"),
    path("cookies/", views.cookie_policy, name="cookie_policy"),
    path(
        "refund-policy/",
        views.refund_policy,
        name="refund_policy",
    ),
    path(
        "listings/<int:pk>/",
        views.listing_detail,
        name="listing_detail",
    ),
    path(
        "listings/<int:pk>/request-quote/",
        views.request_quote,
        name="request_quote",
    ),
    path(
        "my-quote-requests/",
        views.my_quote_requests,
        name="my_quote_requests",
    ),
    path(
        "buyer/dashboard/",
        views.buyer_dashboard,
        name="buyer_dashboard",
    ),
    path(
        "buyer/orders/",
        views.buyer_orders,
        name="buyer_orders",
    ),
    path(
        "manufacturer/dashboard/",
        views.manufacturer_dashboard,
        name="manufacturer_dashboard",
    ),
    path(
        "manufacturer/orders/",
        views.manufacturer_orders,
        name="manufacturer_orders",
    ),
    path(
        "orders/<int:pk>/",
        views.order_detail,
        name="order_detail",
    ),
    path(
        "orders/<int:pk>/messages/send/",
        views.send_order_message,
        name="send_order_message",
    ),
    path(
        "orders/<int:pk>/review/",
        views.review_order,
        name="review_order",
    ),
    path(
        "milestones/<int:pk>/complete/",
        views.mark_milestone_complete,
        name="mark_milestone_complete",
    ),
    path(
        "milestones/<int:pk>/fund/",
        views.fund_milestone,
        name="fund_milestone",
    ),
    path(
        "milestones/<int:pk>/start/",
        views.start_milestone,
        name="start_milestone",
    ),
    path(
        "milestones/<int:pk>/respond/",
        views.respond_to_milestone,
        name="respond_to_milestone",
    ),
    path(
        "milestones/<int:pk>/release/",
        views.release_milestone_payment,
        name="release_milestone_payment",
    ),
    path(
        "manufacturer/quotes/<int:pk>/status/",
        views.update_quote_status,
        name="update_quote_status",
    ),
    path(
        "manufacturer/listings/create/",
        views.create_listing,
        name="create_listing",
    ),
    path(
        "manufacturer/listings/",
        views.my_listings,
        name="my_listings",
    ),
    path(
        "manufacturer/listings/<int:pk>/edit/",
        views.edit_listing,
        name="edit_listing",
    ),
    path(
        "manufacturer/quotes/<int:pk>/send/",
        views.send_quotation,
        name="send_quotation",
    ),
    path(
        "quotations/<int:pk>/respond/",
        views.respond_to_quotation,
        name="respond_to_quotation",
    ),
    path(
        "saved-listings/",
        views.saved_listings,
        name="saved_listings",
    ),
    path(
        "listings/<int:pk>/save/",
        views.save_listing,
        name="save_listing",
    ),
    path(
        "saved-listings/<int:pk>/remove/",
        views.remove_saved_listing,
        name="remove_saved_listing",
    ),
    path(
        "manufacturers/<int:pk>/",
        views.manufacturer_profile,
        name="manufacturer_profile",
    ),
    path(
        "manufacturer/profile/edit/",
        views.edit_business_profile,
        name="edit_business_profile",
    ),
    path(
        "notifications/",
        views.notifications,
        name="notifications",
    ),
    path(
        "notifications/<int:pk>/open/",
        views.open_notification,
        name="open_notification",
    ),
    path(
        "notifications/read-all/",
        views.mark_all_notifications_read,
        name="mark_all_notifications_read",
    ),
]
