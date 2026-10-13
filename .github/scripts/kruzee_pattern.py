#!/usr/bin/env python3
"""Decide how many commits the daily bot makes so the contribution graph spells KRUZEE.

The letters are drawn with empty days. Every other day gets commits.
GitHub's graph has one column per week, starting on Sunday. Week N here is the
week that starts on the Nth Sunday of the year.

Usage:
  kruzee_pattern.py                  commits to make today (UTC)
  kruzee_pattern.py --date 2027-03-14
  kruzee_pattern.py --preview 2027   draw the year's grid in the terminal
"""
import argparse
import datetime as dt
import random

TEXT = "KRUZEE"
START_WEEK = 2  # week 1 is skipped
GAP_WEEKS = 3   # full weeks of activity between letters

# Each letter is 7 rows (Sunday to Saturday). Each column is one week.
# '#' is an empty day, '.' is a day with commits.
GLYPHS = {
    "K": ["#...#",
          "#..#.",
          "#.#..",
          "##...",
          "#.#..",
          "#..#.",
          "#...#"],
    "R": ["#####",
          "#...#",
          "#...#",
          "#####",
          "#.#..",
          "#..#.",
          "#...#"],
    "U": ["#...#",
          "#...#",
          "#...#",
          "#...#",
          "#...#",
          "#...#",
          "#####"],
    "Z": ["######",
          ".....#",
          "....#.",
          "...#..",
          "..#...",
          ".#....",
          "######"],
    "E": ["#####",
          "#....",
          "#....",
          "####.",
          "#....",
          "#....",
          "#####"],
}

# Background days get a random number of commits from 1 to 100.
MIN_COMMITS, MAX_COMMITS = 1, 100


def build_empty_days():
    """Lay the letters out left to right as a set of (week, day) pairs."""
    empty = set()
    week = START_WEEK
    for letter in TEXT:
        glyph = GLYPHS[letter]
        for day, row in enumerate(glyph):
            for col, cell in enumerate(row):
                if cell == "#":
                    empty.add((week + col, day))
        week += len(glyph[0]) + GAP_WEEKS
    return empty


EMPTY_DAYS = build_empty_days()


def week_and_day(date):
    """Return (week number, day of week with Sunday = 0)."""
    jan1 = dt.date(date.year, 1, 1)
    first_sunday = jan1 + dt.timedelta(days=(6 - jan1.weekday()) % 7)
    day = (date.weekday() + 1) % 7
    if date < first_sunday:
        return 0, day
    return (date - first_sunday).days // 7 + 1, day


def is_letter_day(date):
    return week_and_day(date) in EMPTY_DAYS


def commits_for(date):
    if is_letter_day(date):
        return 0
    return random.randint(MIN_COMMITS, MAX_COMMITS)


def preview(year):
    """Print the year like the contribution graph. '#' = empty letter day."""
    jan1 = dt.date(year, 1, 1)
    start = jan1 - dt.timedelta(days=(jan1.weekday() + 1) % 7)  # Sunday on or before Jan 1
    rows = [[] for _ in range(7)]
    d = start
    while d.year <= year:
        mark = " " if d.year < year else ("#" if is_letter_day(d) else ".")
        rows[(d.weekday() + 1) % 7].append(mark)
        d += dt.timedelta(days=1)
    for name, row in zip(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], rows):
        print(f"{name} {''.join(row)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=dt.date.fromisoformat)
    parser.add_argument("--preview", type=int, metavar="YEAR")
    args = parser.parse_args()
    if args.preview:
        preview(args.preview)
        return
    date = args.date or dt.datetime.now(dt.timezone.utc).date()
    print(commits_for(date))


if __name__ == "__main__":
    main()
