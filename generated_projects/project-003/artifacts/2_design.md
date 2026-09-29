# System Design Artifact (Stage 2) — project-003

- **System Type:** `Frontend web application`

## Architecture Overview
A single-page web application that runs entirely in the user's browser. It uses local browser storage (LocalStorage) to persist step data, eliminating the need for a backend server or database. The application logic handles input validation, data storage, and the calculation of suggestions based on historical data.

## Technology Choices

| Category | Technology | Rationale |
|---|---|---|
| **Frontend** | `HTML/CSS/JS` | Simple, lightweight, and sufficient for a browser-based mobile-optimized interface. |
| **Database** | `LocalStorage` | Meets the V1 requirement for data persistence without the complexity of a backend server. |

## Components

| Component ID | Name | Responsibility | Requirements |
|---|---|---|---|
| `COMP-01` | Step Logger UI | Provides an interface for users to input daily step counts and validates input format. | FR-01, FR-02, NFR-01, NFR-02 |
| `COMP-02` | Data Persistence Manager | Manages reading and writing of step data to the browser's LocalStorage. | FR-01, NFR-03 |
| `COMP-03` | Suggestion Engine | Calculates the 7-day average of steps and generates personalized feedback for the user. | FR-03 |

## Data Model & Entities

### Entity: `DailyStepRecord` (`ENT-01`)
- **Purpose**: Stores the step count for a specific date.
- **Attributes**: `date, step_count`

## Design Decisions

- **[DD-01] Use browser LocalStorage for data persistence.**: Simplifies architecture by removing the need for a backend and user accounts for V1.
- **[DD-02] Client-side validation of inputs.**: Ensures immediate feedback for the user and prevents invalid data from being stored.

