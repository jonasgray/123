# State Department Travel Advisory Agent

A small Python agent that checks the U.S. State Department travel advisory
feed and returns destination-specific risk information.

The agent maps each destination to the State Department's four advisory levels:

| Level | Label | Meaning |
| --- | --- | --- |
| 1 | Exercise Normal Precautions | The lowest level of risk, though some safety risks may exist. |
| 2 | Exercise Increased Caution | Be aware of heightened risks to safety and security. |
| 3 | Reconsider Travel | Avoid travel due to serious risks. |
| 4 | Do Not Travel | The highest level of risk, typically indicating life-threatening conditions or a high likelihood of danger. |

## Usage

Run the CLI with a destination:

```bash
python3 -m travel_advisory_agent "Haiti"
```

Or run it without arguments and enter the destination when prompted:

```bash
python3 -m travel_advisory_agent
```

Example output:

```text
Destination: Haiti
Risk Level: Level 4 - Do Not Travel
Guidance: The highest level of risk, typically indicating life-threatening conditions or a high likelihood of danger.
Published: Thu, 16 Apr 2026
Source: https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories/haiti-travel-advisory.html
Summary: Do Not Travel to Haiti due to the risk of crime, terrorism, kidnapping, unrest, and limited health care...
```

## Development

Run tests with:

```bash
python3 -m unittest discover -s tests
```
