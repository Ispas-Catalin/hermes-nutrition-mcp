# Hermes Nutrition MCP Instructions

This file is for the Hermes agent. It explains how to use the local `nutrition-mcp` server for nutrition tracking.

## MCP Server

Use this MCP server:

```yaml
mcp_servers:
  nutrition:
    url: "http://192.168.1.142:8765/mcp"
    headers:
      Authorization: "Bearer <REAL_MCP_TOKEN>"
```

Do not store the real token in chat history, prompts, notes, or long-term memory.

The server should be deployed with this environment variable:

```text
PUBLIC_HOSTS=192.168.1.142,nutrition-mcp
```

This allows Hermes to connect with `Host: 192.168.1.142:8765` while MCP DNS rebinding protection remains enabled.

Health check:

```text
Call the nutrition MCP health tool.
```

Expected service details:

```text
db_path: /data/nutrition.db
exports_path: /data/exports
timezone: Europe/Bucharest
```

## Core Rule

The SQLite database is the source of truth.

Do not memorize food macros, aliases, recipe definitions, or historical logs in Hermes memory. When nutrition information is needed, use the MCP tools.

Use memory only for conversational context like "the user is currently talking about lunch" or "the user is correcting the last entry." Persistent nutrition facts belong in the MCP database.

## What The MCP Tracks

The server has three main concepts:

- Foods: individual macro sources, such as Babybel, Greek yogurt, tuna, dough, cheese, sauce.
- Aliases: names the user naturally says, such as `babybel`, `default tuna`, `pizza dough`, `tuna pizza`.
- Recipes: reusable meals made from foods, such as `tuna pizza = 165g dough + 60g tuna + 40g cheese`.

Logged meal entries store snapshots. If a food or recipe is updated later, old logs do not change.

Tracked nutrients are calories, protein, carbs, fat, fiber, sugars, saturated fat, and salt. Salt is `salt_g` from labels in grams, not sodium in milligrams. If a label only gives sodium, ask before storing it or convert sodium to salt explicitly.

## Tool Use Principles

Before logging a vague food, search first:

```text
get_food(alias="...") if the user gives an exact known alias
search_foods(query="...")
search_recipes(query="...")
list_aliases(query="...")
```

If an alias exists, use it. If it does not exist, ask the user for enough macro data to create the food or recipe.

Do not guess macros for new foods unless the user explicitly asks for an estimate and accepts that it is an estimate. Prefer asking for the label or known macro values.

If the user asks what foods are already known and does not know what to search for, use:

```text
list_foods()
```

## Common Workflows

### Add A Simple Food

Use `add_food` when the user gives macros for a standalone food.

Example user message:

```text
Add Babybel. One piece is 70 kcal, 4g protein, 0g carbs, 5g fat. Alias babybel.
```

Tool call:

```json
{
  "name": "Babybel",
  "serving_name": "1 piece",
  "kcal": 70,
  "protein_g": 4,
  "carbs_g": 0,
  "fat_g": 5,
  "fiber_g": 0,
  "sugars_g": 0,
  "saturated_fat_g": 0,
  "salt_g": 0,
  "aliases": ["babybel"]
}
```

When a label includes sugars, saturated fat, or salt, pass them as:

```json
{
  "sugars_g": 0.7,
  "saturated_fat_g": 16.8,
  "salt_g": 1.4
}
```

### Add A Food Measured In Grams

For ingredients usually measured by weight, store macros per `100 g`.

Example:

```json
{
  "name": "Default tuna",
  "serving_name": "100 g",
  "grams_per_serving": 100,
  "kcal": 120,
  "protein_g": 26,
  "carbs_g": 0,
  "fat_g": 1,
  "fiber_g": 0,
  "sugars_g": 0,
  "saturated_fat_g": 0,
  "salt_g": 0,
  "aliases": ["default tuna", "tuna"]
}
```

Then logging `60g tuna` should call:

```json
{
  "alias": "default tuna",
  "grams": 60
}
```

### Log A Known Food

Example:

```text
I ate 2 babybel.
```

Tool call:

```json
{
  "alias": "babybel",
  "quantity": 2,
  "raw_message": "I ate 2 babybel."
}
```

If the user gives grams:

```json
{
  "alias": "default tuna",
  "grams": 60,
  "raw_message": "I ate 60g tuna."
}
```

### Create A Homemade Recipe

Use recipes for repeated homemade meals.

Example user message:

```text
My tuna pizza is 165g pizza dough, 60g default tuna, and 40g cheese.
```

First ensure each ingredient exists as a food with aliases. Then call:

```json
{
  "name": "Tuna pizza",
  "aliases": ["tuna pizza"],
  "ingredients": [
    {"alias": "pizza dough", "grams": 165},
    {"alias": "default tuna", "grams": 60},
    {"alias": "cheese", "grams": 40}
  ]
}
```

### Log A Recipe

Example:

```text
I ate a tuna pizza.
```

Tool call:

```json
{
  "alias": "tuna pizza",
  "raw_message": "I ate a tuna pizza."
}
```

### Log A Recipe With Adjustments

Example:

```text
I ate a tuna pizza, but with 20g more cheese.
```

Tool call:

```json
{
  "alias": "tuna pizza",
  "adjustments": [
    {"alias": "cheese", "delta_grams": 20}
  ],
  "raw_message": "I ate a tuna pizza, but with 20g more cheese."
}
```

Example:

```text
I ate a tuna pizza but only used 30g cheese.
```

Tool call:

```json
{
  "alias": "tuna pizza",
  "adjustments": [
    {"alias": "cheese", "grams": 30}
  ],
  "raw_message": "I ate a tuna pizza but only used 30g cheese."
}
```

Example:

```text
I ate half a tuna pizza.
```

Tool call:

```json
{
  "alias": "tuna pizza",
  "quantity": 0.5,
  "raw_message": "I ate half a tuna pizza."
}
```

## Corrections

If the user corrects the last logged quantity, search/get the day first, identify the exact entry, then call `update_entry`.

Example:

```text
Actually that was 3 babybel, not 2.
```

Tool flow:

```text
get_day(date=<today if omitted>)
update_entry(entry_id=<matching entry id>, quantity=3)
```

If the user says to remove an entry, use `delete_entry` only when the exact entry is clear.

Never bulk delete.

## Daily Review

When the user asks what they ate today:

```text
get_day()
```

Return the MCP table and a concise summary of totals.

When the user asks about a date range:

```text
get_entries(from_date="YYYY-MM-DD", to_date="YYYY-MM-DD")
```

Use this for questions like "what did I eat this week?" if a custom range is requested.

When the user asks for this week or a weekly trend:

```text
get_weekly_report(date=<any date in that week, optional>)
```

The week is Monday through Sunday.

When the user asks to finalize/export the day:

```text
finalize_day()
```

Mention that markdown, CSV, and JSON exports were written under `/data/exports`.

## Cleaning Up Foods And Recipes

Use cleanup tools only for clear typos or duplicates.

```text
delete_food(food_id=<exact id>)
delete_recipe(recipe_id=<exact id>)
```

These tools are intentionally conservative. They should fail if the food or recipe has logged entries or is still used by another recipe. If deletion fails, explain why and suggest updating aliases or names instead.

## Error Handling

If the MCP says an alias was not found:

1. Search similar foods and recipes.
2. If no good match exists, ask the user whether to add it.
3. Ask for serving size and macros if needed.

Good response:

```text
I do not have "protein pudding" saved yet. What are the calories, protein, carbs, and fat per serving or per 100g?
```

If a duplicate alias error happens, search aliases and tell the user what it already points to.

## Agent Style

Be concise. Confirm logged foods with totals when useful.

Good response after logging:

```text
Logged: 2 Babybel. Today so far: 140 kcal, 8.0g protein, 0.0g carbs, 10.0g fat.
```

For recipes, mention adjustments:

```text
Logged: tuna pizza with +20g cheese. Today so far: ...
```

Do not expose raw tokens. Do not mention internal implementation details unless the user asks.
