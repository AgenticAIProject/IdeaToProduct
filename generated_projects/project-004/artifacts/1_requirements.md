# Requirements Artifact (Stage 1) — project-004

**Problem Statement:**
> Casual walkers lack a simple, centralized way to monitor their daily physical activity and hydration levels to support general health goals.

## Objectives
- Enable users to log and track daily step counts.
- Enable users to log and track daily water intake.
- Provide a clear, accessible browser-based dashboard for health data visualization.

## User Stories

| ID | Priority | Actor | User Story |
|---|---|---|---|
| `US-01` | **Must** | Casual Walker | As a casual walker, I want to log my daily step count, so that I can monitor my physical activity levels. |
| `US-02` | **Must** | Casual Walker | As a casual walker, I want to log my daily water intake, so that I can ensure I am staying hydrated. |
| `US-03` | **Must** | Casual Walker | As a casual walker, I want to view a dashboard of my daily activity and hydration, so that I can track my progress over time. |

## Functional Requirements

| ID | Priority | Description | Related Stories |
|---|---|---|---|
| `FR-01` | **Must** | The system shall allow the user to input a numerical value for daily steps. | US-01 |
| `FR-02` | **Must** | The system shall allow the user to input a numerical value for daily water intake in milliliters. | US-02 |
| `FR-03` | **Must** | The system shall display a dashboard summarizing the current day's steps and water intake. | US-03 |
| `FR-04` | **Must** | The system shall validate that all user-provided numerical inputs are positive integers. | US-01, US-02 |

## Acceptance Criteria

- **[AC-01]** (Validates `FR-01`): Given the user is on the input page, When they enter a positive integer for steps, Then the system saves the value successfully.
- **[AC-02]** (Validates `FR-04`): Given the user attempts to enter a negative number or text, When they submit the form, Then the system displays an error message and rejects the input.
- **[AC-03]** (Validates `FR-03`): Given the user has logged data, When they navigate to the dashboard, Then the system displays the correct totals for the current date.

## Non-Functional Requirements

- **[Security]** The system shall sanitize all user inputs to prevent injection attacks, ensuring no malicious scripts are executed via the dashboard.
- **[Usability]** The dashboard shall be responsive and accessible via standard modern web browsers.
- **[Reliability]** The system shall ensure data integrity by rejecting non-numeric or negative values during input.

## Grounding Evidence (GitHub / Public Issues)

- **[event-stream]**: I don't know what to say.
- **[Rocket]**: Compile with stable Rust
- **[terminal]**: Feature Request: sixel graphics support

