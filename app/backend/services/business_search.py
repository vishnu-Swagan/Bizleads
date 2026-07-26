"""Filter vocabulary for the discovery UI.

This module once asked a language model to invent businesses matching a
search, and returned them as leads. Plausible names, plausible websites,
none of them real. Discovery now goes to a licensed provider
(services/mapbox_places.py) and this file holds only the category and
country lists the filter dropdowns render.

The generator is deleted rather than left unused: a fabricated business
presented as a lead is the one failure this product cannot survive, and
dead code that does exactly that is an invitation to call it.
"""
import logging
from typing import Dict, Any, List, Optional


logger = logging.getLogger(__name__)


# Available categories and countries for filter dropdowns
BUSINESS_CATEGORIES = [
    "Restaurant", "Retail", "Healthcare", "Automotive", "Construction",
    "Food & Beverage", "Beauty & Spa", "Fitness", "Legal Services",
    "Accounting", "Real Estate", "Education", "Photography",
    "Plumbing", "Electrical", "Landscaping", "Cleaning Services",
    "Pet Services", "Bakery", "Coffee Shop", "Dentistry",
    "Veterinary", "Florist", "Dry Cleaning", "Tattoo Studio",
    "Barbershop", "Tailor", "Jewelry Store", "Furniture Store",
    "Hardware Store", "Pharmacy", "Optician", "Physiotherapy",
    "Yoga Studio", "Martial Arts", "Dance Studio", "Music School",
    "Driving School", "Printing Services", "Car Wash"
]

COUNTRIES_LIST = [
    "United States", "United Kingdom", "Canada", "Australia", "Germany",
    "France", "Spain", "Italy", "Japan", "Brazil", "India", "Mexico",
    "South Africa", "Nigeria", "UAE", "Singapore", "South Korea",
    "Argentina", "Colombia", "Thailand", "Netherlands", "Sweden",
    "Norway", "Denmark", "Poland", "Turkey", "Egypt", "Kenya",
    "Philippines", "Indonesia", "Vietnam", "Malaysia", "New Zealand",
    "Ireland", "Portugal", "Greece", "Czech Republic", "Austria",
    "Switzerland", "Belgium", "Chile", "Peru", "Pakistan", "Bangladesh"
]
