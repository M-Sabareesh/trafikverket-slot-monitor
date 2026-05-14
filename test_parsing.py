#!/usr/bin/env python3
"""Test the slot parsing from HTML."""

from bs4 import BeautifulSoup
import re

# Sample HTML from the Trafikverket page
html = '''<section id="results-desktop"><div class="panel mb-3"><div class="panel-body"><div class="row"><div class="col-9"><div class="row"><div class="col-6"><strong>onsdag 10 jun 2026,&nbsp;08:00</strong><br>Göteborg-Hisingen </div><div class="col-6"> Körprov B<br><span class="text-muted">1&nbsp;800 kr</span></div></div></div><div class="col-3"><button class="btn btn-primary">Välj</button></div></div></div></div><div class="panel mb-3"><div class="panel-body"><div class="row"><div class="col-9"><div class="row"><div class="col-6"><strong>torsdag 11 jun 2026,&nbsp;07:15</strong><br>Göteborg-Hisingen </div><div class="col-6"> Körprov B<br><span class="text-muted">1&nbsp;800 kr</span></div></div></div><div class="col-3"><button class="btn btn-primary">Välj</button></div></div></div></div><div class="panel mb-3"><div class="panel-body"><div class="row"><div class="col-9"><div class="row"><div class="col-6"><strong>fredag 12 jun 2026,&nbsp;10:30</strong><br>Göteborg-Hisingen </div><div class="col-6"> Körprov B<br><span class="text-muted">1&nbsp;800 kr</span></div></div></div><div class="col-3"><button class="btn btn-primary">Välj</button></div></div></div></div></section>'''

soup = BeautifulSoup(html, 'html.parser')
results_section = soup.find('section', id='results-desktop')

print(f'Found results section: {results_section is not None}')

panels = results_section.find_all('div', class_='panel')
print(f'Found {len(panels)} panels\n')

print("=" * 60)
print("PARSED SLOTS")
print("=" * 60)

for i, panel in enumerate(panels):
    panel_body = panel.find('div', class_='panel-body')
    strong_tag = panel_body.find('strong')
    date_time_text = strong_tag.get_text(strip=True)
    
    # Get location
    col6_div = strong_tag.find_parent('div', class_='col-6')
    full_text = col6_div.get_text(separator=' ', strip=True)
    location = full_text.replace(date_time_text, '').strip()
    
    # Get exam type and price
    row_div = panel_body.find('div', class_='row')
    col6_divs = row_div.find_all('div', class_='col-6')
    info_col = col6_divs[1]
    info_text = info_col.get_text(separator=' ', strip=True)
    
    # Extract exam type
    exam_type = "Körprov B"
    if 'Körprov' in info_text:
        exam_match = re.search(r'Körprov\s*\w*', info_text)
        if exam_match:
            exam_type = exam_match.group(0).strip()
    
    price_span = info_col.find('span', class_='text-muted')
    price = price_span.get_text(strip=True).replace('\xa0', ' ') if price_span else ''
    
    # Parse date/time
    date_pattern = r'(\w+)\s+(\d{1,2})\s+(\w+)\s+(\d{4}),?\s*(\d{2}:\d{2})'
    match = re.search(date_pattern, date_time_text.lower())
    
    if match:
        day_name, day, month_str, year, time = match.groups()
        print(f"\nSlot {i+1}:")
        print(f"  Date: {day_name} {day} {month_str} {year}")
        print(f"  Time: {time}")
        print(f"  Location: {location}")
        print(f"  Exam: {exam_type}")
        print(f"  Price: {price}")

print("\n" + "=" * 60)
