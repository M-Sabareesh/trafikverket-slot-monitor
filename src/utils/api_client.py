class APIClient:
    def __init__(self, base_url):
        self.base_url = base_url

    def fetch_slots(self):
        import requests
        response = requests.get(f"{self.base_url}/slots")
        if response.status_code == 200:
            return self.parse_response(response.json())
        else:
            response.raise_for_status()

    def parse_response(self, response_data):
        slots = []
        for slot in response_data.get('slots', []):
            slots.append({
                'date': slot['date'],
                'time': slot['time'],
                'available': slot['available']
            })
        return slots