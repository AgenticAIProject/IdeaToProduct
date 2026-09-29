# System Design Artifact (Stage 2) — project-004

- **System Type:** `Frontend web application`

## Architecture Overview
A single-page browser-based application that stores health data locally in the user's browser. The application consists of a UI layer for data entry and a dashboard view, with a local storage manager handling persistence. No backend server is required for this V1 scope.

## Technology Choices

| Category | Technology | Rationale |
|---|---|---|
| **Frontend** | `HTML/CSS/JS` | Simplest stack for a browser-based dashboard without backend requirements. |
| **Database** | `LocalStorage` | Provides persistent storage for a single-user local instance without needing a server or database infrastructure. |

## Components

| Component ID | Name | Responsibility | Requirements |
|---|---|---|---|
| `COMP-01` | Input Form Component | Captures user input for steps and water intake, performs client-side validation, and sanitizes inputs. | FR-01, FR-02, FR-04, NFR-01, NFR-03 |
| `COMP-02` | Dashboard Component | Retrieves and displays the current day's health data from local storage. | FR-03, NFR-02 |
| `COMP-03` | Storage Manager | Handles reading and writing of daily health data to the browser's LocalStorage. | FR-01, FR-02, FR-03, ASM-02 |

## Data Model & Entities

### Entity: `DailyHealthLog` (`DE-01`)
- **Purpose**: Stores the steps and water intake for a specific date.
- **Attributes**: `date, steps, waterIntakeMl`

## Design Decisions

- **[DD-01] Use browser LocalStorage for data persistence.**: Eliminates the need for a backend server, keeping the V1 architecture simple and cost-effective.
- **[DD-02] Client-side only architecture.**: The requirements do not specify multi-user support or cloud synchronization, making a client-side app sufficient.

