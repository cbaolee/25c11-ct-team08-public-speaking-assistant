---
topic: "User Acceptance Testing Briefing"
category: "Technology"
duration_min: 7
---
Good {{ time_of_day }}, everyone. My name is {{ speaker_name }}, and I'm {{ speaker_role }} on the {{ project_name }} project. Over the next {{ uat_duration }}, you'll be doing something really important: user acceptance testing, or UAT for short. In the next few minutes, I'll explain what that means, how it will work, and what we need from you.

Let's start with the most important question: what is UAT, and why do we need you?

Before today, our own team has already tested the system thoroughly. We've checked that buttons work, calculations are correct, and pages load properly. But there's one thing we can't fully test ourselves: whether the system actually works for your real, day-to-day work. You're the experts in your business processes, not us. So the purpose of UAT is for you to confirm that the system does what you need, in the way you need it, before it goes live.

In other words, you're not here to test whether the code is perfect. You're here to answer one question: "Can I do my job with this system?"

Now, let me explain how it will work.

Testing will run from {{ uat_start_date }} to {{ uat_end_date }}. You'll be testing in a special test environment, which is a copy of the system that's completely separate from the live one. So please don't worry about breaking anything. In fact, if you can break it, we'd like to know! You can access it at {{ test_environment_access }}. Your login details will be sent to you {{ login_delivery_method }}.

One important rule: please only use the test data we've provided, and never enter real customer personal data, like real names, phone numbers, or ID numbers, into the test system.

Each of you has been assigned a set of test scenarios, based on your role. {{ scenario_assignment_details }} Each scenario describes a real task, step by step, with the result you should expect. For example, {{ example_scenario }}

Please follow the steps carefully, and then mark each scenario as "passed" or "failed" in {{ tracking_tool }}. And here's a tip: after you finish the written steps, try doing things the way you'd naturally do them at work. Use the shortcuts you'd use, make the mistakes people sometimes make, and try unusual cases. Those are often where the most important problems hide.

Now, what should you do when you find a problem?

Please report it in {{ tracking_tool }} as soon as possible. A good report includes four things: the steps you took, so we can repeat them; what you expected to happen; what actually happened; and a screenshot, if possible. A report like "it doesn't work" is very hard for us to act on. But a report like "When I click 'Save' on the invoice page after adding a discount, I get an error message, and the invoice isn't saved," with a screenshot, lets us fix it much faster.

Please also choose a severity level. Critical means you can't complete an important task at all, and there's no workaround. High means a major function doesn't work correctly, but there's a workaround. Medium means something is wrong, but it doesn't stop your work. And low means small issues, like a typo or a layout problem.

There's one more distinction I'd like to explain. Sometimes, during testing, you'll think: "It works as designed, but I wish it worked differently," or "It would be great if it also did this." That's very valuable feedback, but it's not a defect. It's a change request. Please still log it, just choose the "suggestion" category. We'll review all suggestions with your managers after UAT and decide which ones to include before or after go-live.

During the testing period, our team will be available to support you. {{ support_arrangement }} And we'll have a short check-in call every {{ checkin_schedule }} to go through new issues and answer questions.

Finally, how do we decide that UAT is complete?

UAT will be considered successful when all scenarios have been tested, there are no open critical or high-severity defects, and {{ sign_off_person }} has formally signed off. That sign-off is the green light for go-live, which is currently planned for {{ go_live_date }}.

I know you all have your regular work to do as well, so we really appreciate the time you're giving to this. Your input now will make a huge difference to how well the system works for you and your colleagues after launch.

Five reminders to take with you: test your scenarios, think like a real user, report problems with clear steps and screenshots, separate defects from suggestions, and ask us whenever you need help.

Anything unclear before you start testing?
