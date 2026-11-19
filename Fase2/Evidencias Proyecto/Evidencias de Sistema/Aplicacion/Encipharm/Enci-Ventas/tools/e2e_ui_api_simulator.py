import os
import sys
import time
import requests

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
TEST_EMAIL = "vendedor.demo@enci.cl"
TEST_PASSWORD = "password123"

class ClientSimulator:
    def __init__(self, platform):
        self.platform = platform
        self.session = requests.Session()
        self.session.headers.update({"X-Enci-Client": platform})
        self.token = None

    def _request(self, method, endpoint, **kwargs):
        url = f"{API_URL}{endpoint}"
        if self.token:
            kwargs.setdefault("headers", {})["Authorization"] = f"Bearer {self.token}"
        
        print(f"[{self.platform.upper()}] {method} {endpoint}")
        res = self.session.request(method, url, **kwargs)
        if res.status_code >= 400:
            print(f"  ❌ ERROR {res.status_code}: {res.text}")
        else:
            print(f"  ✅ SUCCESS {res.status_code}")
        return res

    def login(self):
        print(f"\n--- Probando Login para {self.platform} ---")
        res = self._request("POST", "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        if res.ok:
            self.token = res.json().get("access_token")
            print("  Token obtenido exitosamente.")
        return res.ok

    def test_dashboard(self):
        print(f"\n--- Probando Dashboard para {self.platform} ---")
        self._request("GET", "/dashboard/vendedor")

    def test_clientes(self):
        print(f"\n--- Probando Clientes para {self.platform} ---")
        self._request("GET", "/clientes")

    def test_oportunidades(self):
        print(f"\n--- Probando Oportunidades para {self.platform} ---")
        self._request("GET", "/oportunidades")

def run_tests():
    try:
        requests.get(f"{API_URL}/health", timeout=2)
    except:
        print(f"Asegurate de que la API este corriendo en {API_URL}")
        return
        
    print("Iniciando Pruebas E2E de UI API Simulation\n")
    
    web_client = ClientSimulator("web")
    if web_client.login():
        web_client.test_dashboard()
        web_client.test_clientes()
        web_client.test_oportunidades()
        
    print("\n===================================\n")
        
    mobile_client = ClientSimulator("mobile")
    if mobile_client.login():
        mobile_client.test_dashboard()
        mobile_client.test_clientes()
        mobile_client.test_oportunidades()

if __name__ == "__main__":
    run_tests()
