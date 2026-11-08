---
topic: "Object-Oriented Programming Pillars"
category: "Technology"
duration_min: 14
---
If a program can be written perfectly well with just functions and variables, why did our industry bother to invent objects at all? It's a fair question, and many people quietly wonder about it. Good {{ time_of_day }}, everyone, and thank you for joining this session of {{ event_or_course_name }}. I'm {{ speaker_name }}, and over the next quarter of an hour or so, we're going to answer that question by exploring one of the most influential ideas in software development: object-oriented programming, and in particular, its four pillars.

If you've written code in languages like Java, C++, C#, or Python, you've almost certainly used objects, even if no one ever explained why they exist. So today, I don't just want to tell you what the four pillars are. I want to show you what problem each one solves, because once you understand the problem, the concept starts to make sense.

Some history first.

In the early days, many programs were written in a procedural style: a long list of instructions and functions operating on shared data. That works fine for small programs. But as software grew to hundreds of thousands of lines, a serious problem appeared. Data could be changed from anywhere. Fixing a bug in one place broke something in another place. Teams stepped on each other's toes. Programs became hard to understand, hard to test, and very hard to change.

Object-oriented programming was a response to that problem. Its central idea is simple: instead of separating data and the functions that work on it, we bundle them together into units called objects. Each object represents a thing, real or abstract, that has its own data and its own behavior.

Before the pillars, two quick terms. A class is a blueprint. An object is something built from that blueprint. If "Car" is the class, then my car and your car are two different objects of that class. They share the same structure, a color, a speed, a brand, but each one has its own values.

To make everything concrete today, I'll use one running example: our {{ running_example_system }}. Keep this in mind as we go through each pillar.

Pillar one: encapsulation.

Encapsulation means keeping an object's data and the methods that operate on that data together, and, just as importantly, hiding the internal details from the outside world.

Consider a bank account. It has a balance. Now, should any piece of code anywhere in the system be allowed to write "balance equals one million"? Of course not. Instead, the account object keeps its balance private and offers controlled ways to interact with it: a deposit method and a withdraw method. The withdraw method can check that you're not taking out more money than you have. The rules live inside the object, and nobody can bypass them.

A coffee machine works the same way. You press a button and you get coffee. You don't need to know how the water is heated or how the pressure is controlled, and the machine doesn't let you reach inside and adjust the boiler by hand. It gives you a simple interface and protects its internals.

What problem does encapsulation solve, then? It protects data from being changed in invalid ways, and it limits the damage of change. If I later decide to store the balance differently, only the account class needs to change. Every other part of the system keeps calling deposit and withdraw exactly as before.

In practice, this is why we mark fields as private and expose public methods. A useful rule of thumb: make everything as private as possible, and only open up what others really need.

On to the second pillar: abstraction.

Abstraction is closely related to encapsulation, and people often mix them up, so let me be precise. Encapsulation is about hiding the data and protecting it. Abstraction is about hiding complexity, showing only what is essential and leaving out unnecessary detail.

Take driving a car. To drive, you need to know about the steering wheel, the accelerator, and the brake. That's the abstraction the car offers you. You do not need to understand fuel injection, gear ratios, or the electronics of the braking system. All of that complexity exists, but it's hidden behind a simple model.

In code, abstraction often appears as abstract classes and interfaces. Imagine a payment system that supports credit cards, e-wallets, and bank transfers. We can define an abstract idea called "Payment Method" with one essential operation: pay a certain amount. The checkout code only talks to that abstraction. It doesn't care how each method actually connects to a bank or a provider.

The problem abstraction solves is cognitive overload. Our brains can only handle so much detail at once. Abstraction lets us think at the right level. When I'm writing checkout logic, I think about "paying." When I'm writing the e-wallet integration, I think about tokens and API calls. Each person works with the level of detail they actually need.

The difference fits in one sentence: abstraction decides what to show, and encapsulation decides how to protect what is hidden.

The third pillar is inheritance.

Inheritance lets one class acquire the properties and behaviors of another class. The original class is called the parent, base, or superclass. The new one is called the child, derived, or subclass.

Back to vehicles. Cars, motorbikes, and trucks all have a brand, a speed, and the ability to start and stop. Instead of writing that code three times, we can create a general "Vehicle" class and let each specific type inherit from it. Then each child class adds only what makes it different: a truck has a cargo capacity, a motorbike might have a sidecar.

The key test for inheritance is the "is-a" relationship. A car is a vehicle. A savings account is a bank account. If that sentence sounds natural, inheritance may be appropriate.

The problem inheritance solves is duplication. Common behavior is written once in the parent and reused by every child. Fix a bug in the parent, and every child benefits.

However, and this is important, inheritance is also the most commonly misused pillar. Deep inheritance hierarchies, five or six levels down, become fragile. A small change at the top can unexpectedly break classes far below. And sometimes developers use inheritance just to reuse code, even when the "is-a" relationship doesn't truly hold. Making a "Car" class inherit from an "Engine" class, for instance, makes no sense, because a car is not an engine. A car has an engine.

That's why experienced developers often follow the principle: favor composition over inheritance. Composition means building objects out of other objects, a car contains an engine, rather than forcing everything into a family tree. Use inheritance when there's a genuine "is-a" relationship, and use composition for "has-a" relationships.

That leaves the fourth pillar, and in many ways the most powerful one: polymorphism.

The word comes from Greek and means "many forms." In programming, polymorphism means that the same operation can behave differently depending on the object that performs it.

Our payment example makes this concrete. We have one abstract operation: pay. A credit card object implements pay by contacting the card network. An e-wallet implements pay by calling the wallet's API. A bank transfer implements it by generating a transfer request. The checkout code simply says: "payment method, pay this amount." It doesn't know, and doesn't need to know, which kind it's talking to. Each object responds in its own way.

A classroom offers an everyday version. If a teacher says "Please submit your assignment," one student emails a file, another uploads it to the learning portal, and another hands in a printed copy. Same request, different behavior. The teacher doesn't need a separate instruction for every student.

Technically, there are two common forms. The first is method overriding, where a child class provides its own version of a method defined in the parent. This is decided while the program is running, and it's the form we've been discussing. The second is method overloading, where several methods share the same name but take different parameters, such as calculating an area from one number for a square, or from two numbers for a rectangle. In languages like Java and C++, this one is resolved when the code is compiled. Some languages, such as Python, don't support it in the same way.

And what does polymorphism buy us? Extensibility. Suppose next month the business wants to add a new payment method, say, {{ new_feature_example }}. With polymorphism, we create one new class that implements pay. The checkout code doesn't change at all. Without polymorphism, we'd be adding yet another "if" branch to a long chain of conditions scattered throughout the codebase, and every new branch is a new chance for bugs.

This idea, being open to extension but closed to modification, is so valuable that it became one of the well-known SOLID design principles.

Seen side by side, the four pillars turn out to be one connected idea.

Abstraction defines what an object should do, the essential contract. Encapsulation protects how it does it, keeping the internals safe. Inheritance lets related objects share common structure and behavior. And polymorphism lets us treat all those related objects uniformly, while each still behaves in its own correct way.

In our {{ running_example_system }}, that means each component exposes a clean interface, guards its own data, reuses shared logic where it truly makes sense, and can be swapped or extended without rewriting the rest of the system.

Three practical takeaways before I finish.

First, don't treat the pillars as rules to follow blindly. Treat them as tools for managing complexity. If a design is getting harder to understand, ask which pillar could help.

Second, be careful with inheritance. Ask "is-a or has-a?" before you extend a class. When in doubt, choose composition.

Third, design around behavior, not just data. A good object isn't just a box of fields with getters and setters. It's something that knows how to do meaningful work and protects its own rules.

And one honest note: object-oriented programming isn't the only way to build software. Functional programming takes a very different approach, and many modern languages happily mix both styles. The goal is not to be "pure OOP." The goal is to write code that is clear, safe, and easy to change, and the four pillars are a proven way to get there.

In four short phrases: encapsulation protects data, abstraction hides complexity, inheritance enables reuse, and polymorphism enables flexibility. Together, they help us build software that can grow without collapsing under its own weight.

I'll stop here and hand the floor to you: where have these pillars saved you in your own code, and where did they get in your way?
