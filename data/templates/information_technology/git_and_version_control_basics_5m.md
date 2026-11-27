---
topic: "Git and Version Control Basics"
category: "Information Technology"
duration_min: 5
---
Hi everyone, I'm {{ argument_speaker_name }}, and today's topic is Git: a tool you'll use almost every day as a developer, and one that will probably save you from disaster more than once.

Picture a folder on your desktop. Inside it, there's a file called "report." Next to it, "report final." Then "report final version two." Then "report final version two, really final." And, of course, "report final version two, really final, fixed."

If that folder looks familiar, you're in the right room. We laugh at it, but it's a real problem. Which version is the latest? What changed between them? What if two people edited the same file at the same time? And what if you break something and need to go back to yesterday's version?

That's the problem version control solves. In my view, {{ argument_why_version_control_essential }}.

Four key ideas carry most of the weight.

This is the part that confuses many beginners: Git has three areas.

Why do we need the staging area? I would argue that {{ argument_staging_area_discipline }}.

The third key idea is branches. A branch is an independent line of development. Suppose your application is working well, and you want to build a new login feature. Instead of changing the main code directly, you create a new branch, maybe called "login-feature." You can experiment freely there. If it goes badly, you simply delete the branch, and the main code is untouched. If it goes well, you merge it back into the main branch.

Sometimes, when you merge, Git finds that two people changed the same lines of the same file in different ways. My position is that {{ argument_merge_conflicts_are_normal }}.

And this is a good moment to clear up a common confusion: Git and GitHub are not the same thing. Git is the version control tool that runs on your computer. GitHub is a website that hosts Git repositories and adds features for collaboration, like pull requests, code reviews, and issue tracking. A simple analogy: Git is like your camera, and GitHub is like a shared online photo album.

Four good habits will make you a much better teammate.

Pull before you start working, so you're always building on the latest version.

{{ argument_team_or_class_context }}

Learning Git can feel confusing at first, but after a couple of weeks of daily use, it becomes second nature. And one day, when you accidentally delete half your project, you'll be very, very glad you used it.

Your first commit is waiting. Make it a small one.
