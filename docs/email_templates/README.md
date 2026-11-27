# Email templates

The two emails Supabase Auth sends for this app. Both show a 6-digit code that the user types into the app; neither has a link. Supabase can only use these templates when the project has its own SMTP server (see [README.md, Email](../../README.md#email)).

| File | Supabase template | Subject |
| --- | --- | --- |
| `confirm_signup.html` | _Authentication → Email Templates → Confirm signup_ | `Your Public Speaking Assistant code` |
| `reset_password.html` | _Authentication → Email Templates → Reset password_ | `Reset your Public Speaking Assistant password` |

## How to update a template

1. Edit the file here and open it in a browser to check it.
2. In Supabase, open the template, set the subject from the table above, paste the whole file into _Message body_ and save.
3. Send yourself a test: sign up with a new address, or use _Forgot password?_ on Log in.

The file in this folder is the reference: change it here first, then paste it into Supabase.

## Variables

| Variable | Value |
| --- | --- |
| `{{ .Token }}` | The 6-digit code. Required in both templates: the app has no link to click. |
| `{{ .Email }}` | The address the email is sent to. |
| `{{ .Data.display_name }}` | The user's display name, copied from `profiles.display_name` to the account's user metadata at sign up and on every name change. Accounts made before the copy existed have none until they change their name, so the greeting falls back to "Hi,": `{{ if .Data.display_name }}Hi {{ .Data.display_name }},{{ else }}Hi,{{ end }}`. |
| `{{ .SiteURL }}` | The project's _Site URL_ (_Authentication → URL Configuration_). Not used by these templates. |

## Rules that must match the project settings

- **Code length:** _Authentication → Providers → Email → Email OTP Length_ must be 6, the same as `app_constants.toml` `[auth] otp_length`.
- **Expiry:** both templates say "This code expires in 60 minutes". Keep _Email OTP Expiration_ at 3600 seconds, or change the sentence in both files.

## Design

The emails follow the app's look (tokens in `src/web/static/css/base.css`):

- Page `#F7F8FA`, white card with a `#E3E7EE` hairline and 14 px corners, like the app panels.
- Dark top bar `#0B1020` like the Landing top bar, with the logo (blue square, white sound bars, one amber bar) built from table cells, since Gmail blocks SVG.
- Title in EB Garamond, other text in Inter, loaded from Google Fonts; mail apps that block web fonts use Georgia and Arial.
- The code sits in the soft blue panel of the app's code field (`#EAF0FE`, border `#BBD0FB`); the expiry line is a warn pill (`#FEF3C7` / `#92400E`).
- Tables and inline CSS only, at most 560 px wide, so the email looks the same in Gmail, Outlook and on phones.
- No tracking links and no images.
