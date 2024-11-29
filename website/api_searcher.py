"""
Searches for products using various retailer APIs and logs any deals found.

Args:
    city (str): The city to search for products in.
    country (str): The country to search for products in. 
    product (str): The product to search for.
    target_price (float): The target price for the product.
    should_send_email (bool): Whether to send email notifications.
    user_id (int, optional): The ID of the user who requested the search.

Returns:
    list: A list of formatted deal results.
"""
import os
import requests
from datetime import datetime
from dataclasses import dataclass
from typing import List
from geopy.geocoders import Nominatim
from dotenv import load_dotenv
from website.models import ScraperResult, db
from .email_service import send_email

geolocator = Nominatim(user_agent="FindmyPrize_Flask")

@dataclass
class DealFinding:
    store: str
    price: float
    product_name: str
    original_price: float = None
    discount: float = None
    timestamp: datetime = datetime.now()

def search_products(city, country, product, target_price, should_send_email, user_id=None):
    # Your API search implementation here

    # Get location coordinates
    loc = geolocator.geocode(f"{city},{country}")
    latitude = loc.latitude
    longitude = loc.longitude
    
    collected_findings = []
    
    # API endpoints dictionary - can be expanded
    API_ENDPOINTS = {
        'edeka': 'https://www.edeka.de/api/offers',
        # Add more API endpoints here
    }
    
    def process_edeka_response(response_data):
        deals = []
        for item in response_data.get('offers', []):
            price = float(item.get('price', 0))
            if price <= target_price and product.lower() in item.get('name', '').lower():
                deals.append(DealFinding(
                    store='EDEKA',
                    price=price,
                    product_name=item.get('name'),
                    original_price=float(item.get('originalPrice', 0)),
                    discount=item.get('discount')
                ))
        return deals

    def log_deal(finding: DealFinding):
        # Check for duplicates
        for existing in collected_findings:
            if (existing.store == finding.store and 
                existing.price == finding.price and 
                existing.product_name == finding.product_name):
                return

        collected_findings.append(finding)
        
        # Log to database
        existing_result = ScraperResult.query.filter_by(
            store=finding.store,
            price=finding.price,
            product=finding.product_name,
            target_price=target_price,
            city=city,
            country=country,
            user_id=user_id
        ).first()

        if not existing_result:
            scraper_result = ScraperResult(
                store=finding.store,
                price=finding.price,
                product=finding.product_name,
                target_price=target_price,
                city=city,
                country=country,
                email_notification=should_send_email,
                user_id=user_id,
                data=f"Deal found: {finding.product_name} at {finding.store} for €{finding.price}",
                timestamp=finding.timestamp
            )
            db.session.add(scraper_result)
            db.session.commit()

    # Search through each API endpoint
    for retailer, endpoint in API_ENDPOINTS.items():
        try:
            params = {
                'query': product,
                'lat': latitude,
                'lng': longitude
            }
            
            response = requests.get(endpoint, params=params)
            response.raise_for_status()
            
            if retailer == 'edeka':
                deals = process_edeka_response(response.json())
                for deal in deals:
                    log_deal(deal)
            # Add more retailer-specific processors here
            
        except requests.RequestException as e:
            print(f"Error fetching data from {retailer}: {str(e)}")
            continue

    # Send email if deals found
    if collected_findings and should_send_email:
        email_content = format_email_content(collected_findings, product, city, country, target_price)
        subject = f"Deal Alert Summary - {len(collected_findings)} deals found for {product}!"
        send_email(subject, email_content, should_send_email)

    # Format results for web display
    return [
        {
            'store': finding.store,
            'product_name': finding.product_name,
            'price': finding.price,
            'original_price': finding.original_price,
            'discount': finding.discount,
            'timestamp': finding.timestamp,
            'target_price': target_price
        }
        for finding in collected_findings
    ]

def format_email_content(findings, product, city, country, target_price):
    return f"""
    🎯 Deal Alert Summary for {product}
    📍 Location: {city}, {country}
    💰 Target Price: €{target_price:.2f}
    
    Found Deals:
    {''.join(f'''
    🏪 {finding.store}
    📦 {finding.product_name}
    💶 Current Price: €{finding.price:.2f}
    {'📌 Original Price: €' + str(finding.original_price) if finding.original_price else ''}
    {'🏷️ Discount: ' + str(finding.discount) + '%' if finding.discount else ''}
    ⏰ Found at: {finding.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
    {'=' * 50}
    ''' for finding in findings)}
    """
