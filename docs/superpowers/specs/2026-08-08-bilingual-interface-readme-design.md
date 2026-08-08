# Bilingual Interface and README Revision Design

## Objective

Add a complete English and Traditional Chinese interface to the existing S&P 500 Earnings Tracker while keeping English as the first-visit default. Revise the README so that it describes the project, performance, and SEC access approach in objective language, and add an authentic screenshot of the finished English interface.

## Scope

This change covers the user-facing text in `index.html`, lightweight frontend tests for language behavior, one English-interface screenshot, and README copy. It does not translate company names or change the earnings, SEC filing, Bark notification, sorting, search, watchlist, or data-fetching logic.

## Interface Architecture

The site will remain a dependency-free single page. A translation dictionary in the existing frontend will provide `en` and `zh-TW` values for every static and dynamically generated interface string.

The current language will be stored as a small application state value. On first visit, the app will use English. When a user selects another language, the choice will be saved in `localStorage` and restored on later visits. Invalid or missing stored values will fall back to English.

A compact `EN / 中文` control will appear in the page header beside the theme control. Changing language will update the document language attribute, static labels, accessibility text, select-option labels, and dynamically rendered table content without fetching the data again.

## Translation Coverage

The translation dictionary will cover:

- Page title and dashboard heading.
- Theme and language controls.
- Search label, placeholder, clear-search label, and result status.
- Sort label and all four sort options.
- Watchlist filter states.
- Table headers and loading state.
- Countdown badges and empty-result guidance.
- SEC filing history controls, filing types, revenue label, original-filing links, pending states, and unavailable states.
- Data-loading error text and the historical-data console warning.

Company names, tickers, dates, EPS values, revenue values, BMO/AMC symbols, and SEC source content will not be translated or modified.

## State and Rendering

The existing search query, sort selection, watchlist filter, saved tickers, and loaded data remain the source of truth. A language change will update static interface nodes and call the existing filtered rendering path so that visible dynamic strings change immediately.

Changing language must not clear the current search query, change the selected sort order, alter watchlist entries, collapse the currently expanded SEC history row, or make another network request. Expanded-row state will therefore be preserved across the table re-render caused by a language change.

## Accessibility and Failure Handling

The language control will expose an accessible label in the active language. The page's `<html lang>` value will be `en` or `zh-TW` as appropriate. Screen-reader-only labels and button labels will be translated together with visible text.

If saved language state is absent or unsupported, the site will render in English. Existing retry and fallback behavior for data files will remain unchanged; only the user-facing messages will be selected from the active language dictionary.

## README Revision

The README introduction and feature descriptions will be rewritten in measured, factual language. Promotional claims including `institutional-grade`, `Pro-Grade`, `zero lag`, `in seconds`, `precision`, and equivalent exaggerated Chinese wording will be removed or replaced with descriptions of actual behavior.

The SEC Worker section will describe the component as a controlled proxy for cloud-hosted requests. It will state that deployments must provide identifying contact information and follow the SEC Fair Access requirements. It will not describe the proxy as bypassing or circumventing SEC blocking.

Near the top of the README, immediately after the badges and project introduction, the document will include:

1. A screenshot captured from the completed local English interface and stored in the repository.
2. A short `Project Motivation` section explaining that the maintainer independently defined the requirements, used AI assistance during development, and personally tests and maintains the project.

The English and Chinese README sections will remain available, and their claims will be kept consistent.

## Testing and Visual Verification

A lightweight Node test will exercise the frontend language behavior without adding a production framework. Tests will verify:

- English is used when no valid preference exists.
- A valid saved Traditional Chinese preference is restored.
- The language choice is persisted.
- Required translation keys exist in both languages.
- Representative dynamic strings render correctly in English and Traditional Chinese.
- Switching language preserves current search, sorting, watchlist, and expanded-history state.

Existing Python and Node tests will be run to confirm that unrelated data and Bark behavior remain unchanged. The final page will be served locally and checked at desktop and mobile widths in both languages. The committed README screenshot will be captured from the verified English desktop view.

## Acceptance Criteria

- A first-time visitor sees the complete English interface.
- The visitor can switch between English and Traditional Chinese without reloading the page.
- A valid language selection survives a browser refresh.
- All visible and accessible application-owned interface text follows the selected language.
- Search, sorting, watchlist, theme, and SEC history behavior continue to work.
- README wording is factual and contains no instruction to bypass SEC controls.
- README explains the controlled-proxy and SEC Fair Access requirements.
- README includes a real English-interface screenshot and the requested project-motivation statement.
- Automated tests and browser-based visual checks complete without regressions.
