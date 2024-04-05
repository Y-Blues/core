# basic_qrcode.py

import segno

qrcode = segno.make_qr("https://yurplan.com/events/Y-Blues-RELEASE-PARTY-Friends/112500?fbclid=IwAR0TJj8ApLPOXFFCGJ_6AYUeSfNAnQpgrVu6yMCNEsiLxYBaOk9hX82K2RY")
qrcode.save("release_yblues.png", scale=10)