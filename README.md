# Pretech Automation website

A redesign of [pretech.co.in](https://pretech.co.in) for Pretech Automation Pvt. Ltd., Pune: process systems, automation, control panels and Industry 4.0, engineered from concept to commissioning since 1996.

Plain HTML, CSS and JavaScript. No build step.

## Run it

Open `index.html` in Chrome or Edge, or serve the folder:

```bash
python -m http.server 8000
```

then visit http://localhost:8000.

The live 3D cell loads three.js r186 from jsDelivr, so it needs an internet connection. Without one the page still works and the cell window steps aside.

## What's in it

| File | Purpose |
| --- | --- |
| `index.html` | Page structure and content |
| `styles.css` | Palette (brand orange #F48516 on white and graphite), type (IBM Plex Sans and Mono), layout |
| `script.js` | Menu, tabs, client filter, contact form (email or WhatsApp), and the three.js robotic palletising cell |
| `assets/img` | Logo mark, hero plant scene, and photos from Pretech's shop and sites |
| `assets/clients` | Client logos |

## Notes

- The hero plant image (`assets/img/plant-dusk.jpg`) comes from the original site's banner. It appears to be a stock photo, so confirm usage rights before publishing.
- The 3D cell and the IIoT dashboard show simulated, illustrative data and are labelled as such.
- The contact form has no backend. It opens the visitor's email app or WhatsApp with the message filled in.
