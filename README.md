# DragoCogs
Cogs for personal use for Red Discord Bot made with Claude.AI

[p]repo add drago-cogs https://github.com/DragoPrime/drago-cogs<br>
[p]cog install drago-cogs [cog]

Note:
- Some cogs will be in romanian language. If you want to use them, fork them and translate them in your language.
- These cogs are made with Claude.AI. I don't know any coding, so support from me is useless.

# Cogs
| Cog | Description |
| --- | ----------- |
| BenchmarkLeaderboard | <details><summary>Allows users to add, view, and manage benchmarking leaderboards</summary>Allows users to add, view, and manage benchmarking leaderboards</details>
| JellyfinSearch | <details><summary>Lets you search your Jellyfin server</summary>This cog is in romanian language and a custom command to search</details>
| Inara | <details><summary>Display the signature image from Inara</summary>Display the signature image from Inara</details>
| Jellyfin Recommendation | <details><summary>Recommend a title from Jellyfin every Monday at 06:00 PM</summary>This cog is in romanian language and a custom command to recommend</details>
| Calendar Sync | <details><summary>Syncs Discord scheduled events to a Google Calendar</summary>Syncs Discord scheduled events to a Google Calendar</details>

## BenchmarkLeaderboard

**`[p]benchmark add [type] [score]`** - Add a benchmark score

**`[p]benchmark view [type]`** - View the top 10 scores for a specific benchmark

**`[p]benchmark types`** - List all existing benchmark types

**`[p]benchmark delete [type] [@Username]`** - Admin command, delete a specific user's score, delete an entire benchmark type

## JellyfinSearch

**`[p]setjellyfinurl https://your.jellyfin.server`** - Set Jellyfin server URL

**`[p]setjellyfinapi your_api_key`** - Set API key

**`[p]freia [movie or series title]`** - Search the libraries

## Inara

**`[p]inara [user ID]`** - Display sig image

## Jellyfin Recommendation

**`[p]recseturl https://your.jellyfin.server`** - Set Jellyfin server URL

**`[p]recsetapi your_api_key`** - Set API key

**`[p]setrecommendationchannel [#channel]`** - Set channel for recommendations

**`[p]showrecsettings`** - View current settings

**`[p]recomanda`** - Manually trigger the recommendation

## Calendar Sync

**`[p]pipinstall google-api-python-client google-auth-httplib2 google-auth-oauthlib pytz google.api_core`** - Install dependencies

**`[p]calendarset setcalendar <your_calendar_id>`** - Set Google Calendar ID

**`[p]calendarset settimezone <your_timezone>`** - Set TimeZone

**`[p]calendarset credentials`** - Upload your Google service account JSON file when prompted

**`[p]calendarset verify`** - Verify all settings are working

**`[p]calendarset settings`** - Show current settings
