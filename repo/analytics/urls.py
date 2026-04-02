from django.urls import path

from analytics.views import EventAnalyticsSummaryView, EventCheckInDistributionView

urlpatterns = [
    path(
        "events/summary/",
        EventAnalyticsSummaryView.as_view(),
        name="analytics-events-summary",
    ),
    path(
        "events/checkin-distribution/",
        EventCheckInDistributionView.as_view(),
        name="analytics-events-checkin-distribution",
    ),
]
