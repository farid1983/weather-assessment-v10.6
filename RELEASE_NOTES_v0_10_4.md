# Weather Assessment v0.10.4 - release notes

## P50 Microsoft Project XML

The export page now generates a Microsoft Project XML schedule for the P50 representative hindcast year.

### Structure

- One summary task per campaign cycle.
- Cycle names include the associated position range.
- One child task per generated sequence activity.
- Finish-to-start links follow the generated campaign sequence.
- A 24-hour calendar is used for continuous offshore operations.

### Duration fields

- Standard `Duration`: total representative elapsed duration, including downtime.
- Custom `Number1`: **Plan Duration [days]**, based on the simulated productive duration.
- Custom `Number2`: **Downtime [days]**, attributed to the affected activity.
- For every cycle and the complete schedule: Plan Duration + Downtime = representative elapsed duration.

### Traceability fields

The XML also defines Location, Position, Activity ID and Safe-to-safe group custom task fields. Detailed duration and attribution information is included in each task note.

### Companion review output

A CSV task list can be downloaded beside the XML. It contains the same cycle hierarchy, durations, downtime, start and finish dates.
