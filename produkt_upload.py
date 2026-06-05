import os
import webbrowser
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QTextEdit, QPushButton, QFileDialog,
                               QMessageBox, QScrollArea, QGroupBox)
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import Qt, QSize
import requests
from dotenv import load_dotenv

# Laden der Umgebungsvariablen für die geschützte API-Authentifizierung
load_dotenv()

ETSY_API_KEY = os.getenv("ETSY_API_KEY")
ETSY_SHARED_SECRET = os.getenv("ETSY_SHARED_SECRET")
ETSY_AUTH_URL = os.getenv("ETSY_AUTH_URL", "https://www.etsy.com/oauth/connect")
ETSY_TOKEN_URL = os.getenv("ETSY_TOKEN_URL", "https://api.etsy.com/v3/public/oauth/token")


class ProduktUploadWidget(QWidget):
    """
    Sub-Widget für das Produkt-Management. Handhabt die Erfassung lokaler Artikeldaten
    und bildet das logische Interface für den REST-Upload an Marktplatz-Schnittstellen.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.bild_pfad = None
        self.etsy_access_token = None
        self.ebay_access_token = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.btn_back_to_start = QPushButton("◀ Zurück zum Hauptmenü")
        self.btn_back_to_start.setFixedWidth(180)
        layout.addWidget(self.btn_back_to_start)

        # Scrollbereich für kleinere Displays
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # --- SEKTION 1: Produktdaten-Eingabe ---
        self.group_daten = QGroupBox("Artikel-Stammdaten")
        form_layout = QVBoxLayout(self.group_daten)

        form_layout.addWidget(QLabel("Titel / Produktname:"))
        self.le_titel = QLineEdit()
        form_layout.addWidget(self.le_titel)

        form_layout.addWidget(QLabel("Beschreibung:"))
        self.te_beschreibung = QTextEdit()
        form_layout.addWidget(self.te_beschreibung)

        form_layout.addWidget(QLabel("Preis (€):"))
        self.le_preis = QLineEdit()
        form_layout.addWidget(self.le_preis)

        form_layout.addWidget(QLabel("SKU (Lagerhaltungsnummer):"))
        self.le_sku = QLineEdit()
        form_layout.addWidget(self.le_sku)

        # Medienimport
        self.btn_bild_laden = QPushButton("Produktbild hinzufügen")
        self.btn_bild_laden.clicked.connect(self.oeffne_bild_dialog)
        form_layout.addWidget(self.btn_bild_laden)

        self.lbl_bild_voransicht = QLabel("Kein Bild ausgewählt")
        self.lbl_bild_voransicht.setAlignment(Qt.AlignCenter)
        self.lbl_bild_voransicht.setFixedSize(200, 200)
        self.lbl_bild_voransicht.setStyleSheet("border: 1px dashed gray;")
        form_layout.addWidget(self.lbl_bild_voransicht)

        scroll_layout.addWidget(self.group_daten)

        # --- SEKTION 2: API Authentifizierung & Schnittstellen ---
        self.group_api = QGroupBox("Marktplatz-Schnittstellen (Etsy & eBay)")
        api_layout = QVBoxLayout(self.group_api)

        # Etsy Integration
        etsy_btn_layout = QHBoxLayout()
        self.btn_etsy_auth = QPushButton("1. Etsy Verbindung autorisieren")
        self.btn_etsy_auth.clicked.connect(self.starte_etsy_auth)
        self.btn_etsy_upload = QPushButton("2. Zu Etsy hochladen")
        self.btn_etsy_upload.clicked.connect(self.upload_zu_etsy)
        etsy_btn_layout.addWidget(self.btn_etsy_auth)
        etsy_btn_layout.addWidget(self.btn_etsy_upload)
        api_layout.addLayout(etsy_btn_layout)

        # eBay Integration
        ebay_btn_layout = QHBoxLayout()
        self.btn_ebay_auth = QPushButton("1. eBay Verbindung autorisieren")
        self.btn_ebay_auth.clicked.connect(self.starte_ebay_auth)
        self.btn_ebay_upload = QPushButton("2. Zu eBay hochladen")
        self.btn_ebay_upload.clicked.connect(self.upload_zu_ebay)
        ebay_btn_layout.addWidget(self.btn_ebay_auth)
        ebay_btn_layout.addWidget(self.btn_ebay_upload)
        api_layout.addLayout(ebay_btn_layout)

        # Datenverwaltung (CRUD-Platzhalter)
        self.btn_ebay_delete = QPushButton("Produkt von eBay entfernen (über SKU)")
        self.btn_ebay_delete.clicked.connect(self.loesche_ebay_produkt)
        self.btn_ebay_delete.setStyleSheet("background-color: #f44336; color: white;")
        api_layout.addWidget(self.btn_ebay_delete)

        scroll_layout.addWidget(self.group_api)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

    def oeffne_bild_dialog(self):
        pfad, _ = QFileDialog.getOpenFileName(self, "Bild auswählen", "", "Bilder (*.png *.jpg *.jpeg)")
        if pfad:
            self.bild_pfad = pfad
            pixmap = QPixmap(pfad)
            self.lbl_bild_voransicht.setPixmap(
                pixmap.scaled(self.lbl_bild_voransicht.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def starte_etsy_auth(self):
        """
        [WIP] Plant den OAuth 2.0 PKCE-Flow für die Etsy API v3.
        Erzeugt den Autorisierungs-URL-String mit den benötigten Scopes ('listings_w', 'listings_r')
        und öffnet diesen im System-Standardbrowser.
        """
        if not ETSY_API_KEY:
            QMessageBox.critical(self, "Konfigurationsfehler", "ETSY_API_KEY fehlt in den Umgebungsvariablen (.env)")
            return

        # TODO: PKCE Code Challenge Generierung & lokaler Redirect-Server-Callback implementieren
        scopes = "listings_r%20listings_w"
        state = "super_secret_state"
        auth_url = f"{ETSY_AUTH_URL}?response_type=code&client_id={ETSY_API_KEY}&redirect_uri=http://localhost:8080&scope={scopes}&state={state}&code_challenge=challenge&code_challenge_method=S256"

        webbrowser.open(auth_url)

    def upload_zu_etsy(self):
        """
        [WIP] Erstellt ein neues Listing auf Etsy via POST-Request.
        Erwartete Architektur:
        1. POST an /v3/application/shops/{shop_id}/listings mit JSON-Payload (Titel, Beschreibung, Preis, Quantity).
        2. Bei Erfolg: Upload des Binärbilds via Multipart-Form-Data an /v3/application/shops/{shop_id}/listings/{listing_id}/images.
        """
        QMessageBox.information(self, "Etsy Integration",
                                "Etsy API-Upload-Pipeline ist als Entwicklungs-Skelett vorbereitet.")

    def starte_ebay_auth(self):
        """
        [WIP] Initiiert den eBay OAuth-Prozess für die REST Fulfillment & Inventory API.
        Leitet den User zur eBay-Anmeldeseite weiter, um das User-Access-Token abzurufen.
        """
        webbrowser.open("https://auth.ebay.com/oauth2/authorize")

    def upload_zu_ebay(self):
        """
        [WIP] Upload-Skelett für eBay Inventory API.
        Erwarteter Ablauf:
        1. PUT /v3/inventory_item/{sku} -> Erstellt oder aktualisiert das Datenobjekt.
        2. POST /v3/offers -> Generiert das konkrete Verkaufsangebot mit Preis und Marktplatz-ID.
        3. POST /v3/offer/{offerId}/publish -> Schaltet das Angebot live.
        """
        QMessageBox.information(self, "eBay Integration",
                                "eBay Inventory API-Pipeline befindet sich in der Implementierungsphase.")

    def loesche_ebay_produkt(self):
        """
        [WIP] Entfernt ein eBay-Angebot basierend auf der eingegebenen SKU.
        Geplanter Request: DELETE an /v3/inventory_item/{sku} unter Verwendung des OAuth-Tokens.
        """
        sku = self.le_sku.text().strip()
        if not sku:
            QMessageBox.warning(self, "Eingabe fehlt",
                                "Bitte geben Sie eine gültige SKU ein, um das Löschen zu simulieren.")
            return

        QMessageBox.information(self, "eBay REST Schnittstelle", f"DELETE-Request für SKU '{sku}' vorbereitet (WIP).")