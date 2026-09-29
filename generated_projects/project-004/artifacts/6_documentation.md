# Documentation Package Artifact (Stage 6) — project-004

## Project README

# Fitness Tracker

## Overview
Casual walkers often lack a simple, centralized way to monitor their daily physical activity and hydration levels. This Fitness Tracker provides a lightweight, browser-based solution to log steps and water intake, helping users stay on top of their health goals.

## Key Features
- **Manual Logging:** Easily input daily step counts and water intake (in ml).
- **Real-time Dashboard:** View current day's totals at a glance.
- **Data Persistence:** Automatically saves your progress locally in your browser.
- **Input Validation:** Ensures only valid, positive integers are recorded.

## Setup & Installation
1. Clone the repository to your local machine.
2. No installation is required. This is a client-side application.
3. Open `index.html` in any modern web browser.

## Quickstart Guide
1. Open `index.html`.
2. Enter your steps and water intake in the provided form fields.
3. Click 'Submit' to save your data.
4. The dashboard will automatically update to reflect your current daily totals.

## Testing Instructions
To run the backend logic tests:
1. Ensure you have Python installed.
2. Run `python3 test_health_tracker.py` in your terminal.
3. The test suite will verify data storage, input validation, and default dashboard values.

---

## API & Module Reference

## Core Logic Reference

### `StorageManager`
Handles interaction with `window.localStorage`.

- `saveData(date, data)`: Persists a `DailyHealthLog` object to storage.
- `getData(date)`: Retrieves the `DailyHealthLog` for the specified date.

### `InputValidator`
- `validate(steps, water)`: Returns `true` if inputs are positive integers, `false` otherwise.

### Data Model: `DailyHealthLog`
- `date` (string): ISO 8601 date string.
- `steps` (number): Total steps taken.
- `waterIntakeMl` (number): Total water consumed in milliliters.

### Example Usage
```javascript
// Saving data
const log = { steps: 5000, waterIntakeMl: 2000 };
localStorage.setItem('2023-10-27', JSON.stringify(log));

// Retrieving data
const data = JSON.parse(localStorage.getItem('2023-10-27'));
```

---

## Architecture Overview

## System Design
This project follows a client-side-only architecture, eliminating the need for a backend server or external database.

### Components
- **Input Form:** Captures and sanitizes user input.
- **Dashboard:** Renders the current day's data.
- **Storage Manager:** Interfaces with browser `LocalStorage`.

### Technical Decisions
- **LocalStorage:** Chosen for persistence to ensure a zero-infrastructure, single-user experience.
- **Client-side Validation:** Implemented to ensure data integrity before storage, preventing malicious or invalid inputs.

### Edge Cases & Recovery
- **Invalid Input:** The system rejects non-numeric or negative values via client-side logic.
- **Empty State:** If no data exists for the current date, the system defaults to 0 steps and 0ml water.
- **Storage Limits:** In the event `LocalStorage` is disabled, the application will fail gracefully by alerting the user.

---

## User Guide

## User Guide

### For Casual Walkers

#### Logging Daily Activity
1. Navigate to the main page.
2. Locate the 'Log Activity' section.
3. Enter your total steps for the day in the 'Steps' field.
4. Enter your total water intake (in ml) in the 'Water' field.
5. Click the 'Save' button.

#### Viewing Progress
1. The 'Dashboard' section displays your current totals.
2. Data is automatically associated with the current date.
3. If you refresh the page, your data will persist as long as you are using the same browser.

---

## Changelog

# Changelog - V1.0.0

## Initial Release
- Implemented manual step logging functionality.
- Implemented manual water intake logging (ml).
- Created responsive browser-based dashboard.
- Integrated `LocalStorage` for data persistence.
- Added input validation for positive integers.
- Verified system stability with a comprehensive Python-based test suite.

---

