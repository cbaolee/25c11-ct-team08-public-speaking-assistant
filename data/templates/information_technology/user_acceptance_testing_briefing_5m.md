---
topic: "User Acceptance Testing Briefing"
Category: "Information Technology"
duration_min: 5
---
Good {{ argument_time_of_day }}, everyone. My name is {{ argument_speaker_name }}, and I'm {{ argument_speaker_role }} on the {{ argument_project_name }} project. Over the next {{ argument_uat_duration }}, you'll be doing something really important: user acceptance testing, or UAT for short. In the next few minutes, I'll explain what that means, how it will work, and what we need from you.

Let's start with the most important question: what is UAT, and why do we need you?

Before today, our own team has already tested the system thoroughly. But there's one thing we can't fully test ourselves: whether the system actually works for your real, day-to-day work. You're the experts in your business processes, not us. So the purpose of UAT is for you to confirm that the system does what you need, in the way you need it, before it goes live.

Now, let me explain how it will work.

Testing will run from {{ argument_uat_start_date }} to {{ argument_uat_end_date }}. You'll be testing in a special test environment, which is a copy of the system that's completely separate from the live one. So please don't worry about breaking anything. You can access it at {{ argument_test_environment_access }}. Your login details will be sent to you {{ argument_login_delivery_method }}.

One important rule: please only use the test data we've provided, and never enter real customer personal data, like real names, phone numbers, or ID numbers, into the test system.

Each of you has been assigned a set of test scenarios, based on your role. {{ argument_scenario_assignment_details }} Each scenario describes a real task, step by step, with the result you should expect. For example, {{ argument_example_scenario }}

Please follow the steps carefully, and then mark each scenario as "passed" or "failed" in {{ argument_tracking_tool }}. And here's a tip: after you finish the written steps, try doing things the way you'd naturally do them at work. Unusual cases are often where the most important problems hide.

Now, what should you do when you find a problem?

Please report it in {{ argument_tracking_tool }} as soon as possible. A good report includes four things: the steps you took, so we can repeat them; what you expected to happen; what actually happened; and a screenshot, if possible. A report like "When I click 'Save' on the invoice page after adding a discount, I get an error message, and the invoice isn't saved," with a screenshot, lets us fix it much faster.

Please also choose a severity level, from critical, when you can't complete an important task at all and there's no workaround, down to low, for small issues like a typo or a layout problem.

One more distinction. If something works as designed, but you wish it worked differently, that's not a defect. It's a suggestion. Please still log it, using the "suggestion" category, and we'll review all suggestions with your managers after UAT.

During the testing period, our team will be available to support you. {{ argument_support_arrangement }} And we'll have a short check-in call every {{ argument_checkin_schedule }} to go through new issues and answer questions.

Finally, how do we decide that UAT is complete?

UAT will be considered successful when all scenarios have been tested, there are no open critical or high-severity defects, and {{ argument_sign_off_person }} has formally signed off. That sign-off is the green light for go-live, which is currently planned for {{ argument_go_live_date }}.

Five reminders to take with you: test your scenarios, think like a real user, report problems with clear steps and screenshots, separate defects from suggestions, and ask us whenever you need help.

Anything unclear before you start testing?
