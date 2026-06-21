# 🗓️ Smart Scheduler AI Telegram Bot

An intelligent Telegram bot designed to act as a personal time-management assistant. The bot leverages natural language processing to seamlessly schedule, manage, and optimize events directly within the user's Google Calendar.

## Overview

This project demonstrates an end-to-end integration of a conversational interface with external productivity APIs. Users can interact with the bot using natural language to summarize their upcoming day, schedule new meetings, or request complex calendar reorganizations based on their existing schedule and deadlines. 

The bot handles secure OAuth 2.0 authentication for Google Calendar, manages user states via a MongoDB database, and is fully deployed as a live webhook-based application.

## Demo Screenshots
<img src="https://github.com/user-attachments/assets/604de09a-2cfb-4918-917e-9a4bd76a59d4" width="220"> <img src="https://github.com/user-attachments/assets/ddd55b95-83d6-400f-9f98-214dc1186a60" width="220"> <img src="https://github.com/user-attachments/assets/3377472f-d3ef-410f-adcc-98ee89a5e7c3" width="220"> <img src="https://github.com/user-attachments/assets/617adf3c-ae76-4738-9f39-7d6a824e3202" width="220">





## Tech Stack & Architecture
* **Backend Framework:** Python, Flask
* **Database:** MongoDB (User token storage and state management)
* **APIs:** Anthropic Claude API (LLM processing), Telegram Bot API, Google Calendar API (OAuth 2.0)
* **Deployment & Hosting:** Render (Live web server for webhook listening)

## Key Features
* **Natural Language Scheduling:** Converts conversational text into actionable Google Calendar events using Claude's LLM.
* **Smart Calendar Optimization:** Analyzes full schedules to identify bottlenecks and suggest alternative times for tasks and meetings.
* **Secure Authentication Flow:** Generates unique, secure login links for users to authenticate their personal Google accounts.
* **Always-On Webhook:** Configured with a dedicated Flask route and UptimeRobot monitoring to prevent server sleep and ensure instant responses.

## Security Note
For security reasons, sensitive files including `.env`, `client_secret_web.json`, and database connection strings are excluded from this repository.
