# Jingleez Mobile

Native SwiftUI companion for the Jingleez MLB research model. The website remains the detailed research and administration surface; this app presents the daily slate, transparent results, compact model health, alert preferences, and responsible-use information.

## Run locally

1. Start the Flask backend from the repository root with `venv/bin/python app.py`.
2. Open `JingleezMobile.xcodeproj` in Xcode.
3. Select an iPhone Simulator and Run.
4. The Simulator uses `http://127.0.0.1:3000` by default.

For a physical iPhone, enter the Mac's LAN address in Account, or use a hosted HTTPS backend. No API keys or model secrets belong in the iOS application.

## Product boundary

This application is read-only. It does not accept, facilitate, or place wagers; hold funds; connect to sportsbook accounts; or create bet slips. `Research weight` is a model-tracking convention, not a wagering instruction. Official mobile and website records contain one Moneyline and one Total generated only after both official MLB starting lineups are confirmed.
