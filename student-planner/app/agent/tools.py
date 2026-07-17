"""Tool definitions for LLM function calling."""

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_courses",
            "description": "List all courses for the current user. Use this to inspect the current timetable before updating, deleting, correcting, or merging existing courses.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_course",
            "description": "Add a course to the user's schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Course name"},
                    "teacher": {"type": "string", "description": "Teacher name"},
                    "location": {"type": "string", "description": "Course location"},
                    "weekday": {
                        "type": "integer",
                        "description": "Weekday of the course, 1 for Monday through 7 for Sunday",
                        "minimum": 1,
                        "maximum": 7,
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Course start time in HH:MM format",
                        "pattern": "^\\d{2}:\\d{2}$",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "Course end time in HH:MM format",
                        "pattern": "^\\d{2}:\\d{2}$",
                    },
                    "week_start": {"type": "integer", "description": "First active week", "default": 1},
                    "week_end": {"type": "integer", "description": "Last active week", "default": 16},
                    "week_pattern": {
                        "type": "string",
                        "description": "Week recurrence pattern",
                        "enum": ["all", "odd", "even"],
                        "default": "all",
                    },
                    "week_text": {"type": "string", "description": "Human-readable week range"},
                },
                "required": ["name", "weekday", "start_time", "end_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_course",
            "description": "Update one existing course by course ID. Use this to rename or correct imported/OCR course records that already exist in the timetable.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "Course ID"},
                    "name": {"type": "string", "description": "Course name"},
                    "teacher": {"type": "string", "description": "Teacher name"},
                    "location": {"type": "string", "description": "Course location"},
                    "weekday": {
                        "type": "integer",
                        "description": "Weekday of the course, 1 for Monday through 7 for Sunday",
                        "minimum": 1,
                        "maximum": 7,
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Course start time in HH:MM format",
                        "pattern": "^\\d{2}:\\d{2}$",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "Course end time in HH:MM format",
                        "pattern": "^\\d{2}:\\d{2}$",
                    },
                    "week_start": {"type": "integer", "description": "First active week"},
                    "week_end": {"type": "integer", "description": "Last active week"},
                    "week_pattern": {
                        "type": "string",
                        "description": "Week recurrence pattern",
                        "enum": ["all", "odd", "even"],
                    },
                    "week_text": {"type": "string", "description": "Human-readable week range"},
                },
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_course",
            "description": "Delete one course by course ID. Use this after confirmation when removing a duplicate or mistaken existing course.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "Course ID"},
                },
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_free_slots",
            "description": "Return the user's free time slots within a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                    "min_duration_minutes": {
                        "type": "integer",
                        "description": "Minimum slot length in minutes",
                        "default": 30,
                    },
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_study_plan",
            "description": "Generate a structured study plan from exams and available time slots.",
            "parameters": {
                "type": "object",
                "properties": {
                    "exams": {
                        "type": "array",
                        "description": "Exam list",
                        "items": {
                            "type": "object",
                            "properties": {
                                "course_name": {"type": "string"},
                                "exam_date": {"type": "string", "description": "Exam date in YYYY-MM-DD format"},
                                "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                                "scope": {
                                    "type": "string",
                                    "description": (
                                        "Optional exam-specific scope, chapters, units, or topics. "
                                        "Only include this when the user provided scope for this exam."
                                    ),
                                },
                                "weak_areas": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": (
                                        "Optional exam-specific weak areas. "
                                        "Only include items that belong to this exam."
                                    ),
                                },
                            },
                            "required": ["course_name", "exam_date"],
                        },
                    },
                    "available_slots": {"type": "object", "description": "Output from get_free_slots"},
                    "study_context": {
                        "type": "object",
                        "description": (
                            "Optional study-quality context collected before planning. "
                            "Use this to pass exam scope, weak areas, target score, daily study limit, "
                            "and the user's raw notes so the generated tasks are not generic."
                        ),
                        "properties": {
                            "exam_scope": {"type": "string", "description": "Exam scope, chapters, units, or topics"},
                            "weak_areas": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Known weak areas such as listening, writing, formulas, or mistakes",
                            },
                            "target_score": {"type": "string", "description": "Target score, grade, or pass goal"},
                            "daily_study_limit_minutes": {
                                "type": "integer",
                                "description": "Maximum planned study minutes per day",
                                "minimum": 30,
                            },
                            "raw_notes": {"type": "string", "description": "Original user-provided study notes"},
                            "using_defaults": {
                                "type": "boolean",
                                "description": "True if the user explicitly asked to use default assumptions",
                            },
                        },
                    },
                    "strategy": {
                        "type": "string",
                        "enum": ["balanced", "intensive", "spaced"],
                        "description": "Study strategy",
                        "default": "balanced",
                    },
                },
                "required": ["exams", "available_slots"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_work_plan",
            "description": "Generate a staged deadline-oriented plan for assignments, reports, essays, projects, presentations, or lab reports from available time slots. This only creates candidate tasks; confirmed tasks must be written with create_task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "work_items": {
                        "type": "array",
                        "description": "Assignment, report, project, or presentation list",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "description": "Work item title"},
                                "due_date": {"type": "string", "description": "Deadline in YYYY-MM-DD format"},
                                "work_type": {
                                    "type": "string",
                                    "description": "assignment, report, essay, project, presentation, lab report, etc.",
                                },
                                "course_name": {"type": "string", "description": "Related course name if known"},
                            },
                            "required": ["title", "due_date"],
                        },
                    },
                    "available_slots": {"type": "object", "description": "Output from get_free_slots"},
                    "work_context": {
                        "type": "object",
                        "description": (
                            "Optional work-quality context collected before planning. "
                            "Use this to pass deliverable requirements, format, grading focus, current progress, "
                            "daily work limit, and raw user notes."
                        ),
                        "properties": {
                            "requirements": {
                                "type": "string",
                                "description": "Deliverable requirements, format, grading focus, or constraints",
                            },
                            "current_progress": {"type": "string", "description": "What the user has already done"},
                            "daily_work_limit_minutes": {
                                "type": "integer",
                                "description": "Maximum planned work minutes per day",
                                "minimum": 30,
                            },
                            "raw_notes": {"type": "string", "description": "Original user-provided work notes"},
                            "using_defaults": {
                                "type": "boolean",
                                "description": "True if the user explicitly asked to use default assumptions",
                            },
                        },
                    },
                    "strategy": {
                        "type": "string",
                        "enum": ["staged", "front_loaded", "last_mile"],
                        "description": "Work decomposition strategy",
                        "default": "staged",
                    },
                },
                "required": ["work_items", "available_slots"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List tasks in an optional date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "date_to": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create one new task in the user's schedule after confirmation. If the user asks for a reminder for this new task, pass reminder_advance_minutes in this same call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "scheduled_date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "start_time": {"type": "string", "description": "Start time in HH:MM format"},
                    "end_time": {"type": "string", "description": "End time in HH:MM format"},
                    "reminder_advance_minutes": {
                        "type": "integer",
                        "description": "Optional lead time in minutes for a task reminder. Use 0 for an at-time reminder.",
                        "minimum": 0,
                    },
                },
                "required": ["title", "scheduled_date", "start_time", "end_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": (
                "Update one existing task by task ID. Never use this to create a new task. "
                "Use reminder_advance_minutes to create or change the task reminder; "
                "pass null to remove/cancel an existing task reminder when the user says no reminder."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "scheduled_date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "start_time": {"type": "string", "description": "Start time in HH:MM format"},
                    "end_time": {"type": "string", "description": "End time in HH:MM format"},
                    "status": {"type": "string", "enum": ["pending", "completed", "skipped"]},
                    "reminder_advance_minutes": {
                        "type": "integer",
                        "description": (
                            "Optional lead time in minutes for the task reminder. "
                            "Use 0 for an at-time reminder. Pass null to remove/cancel "
                            "the existing task reminder."
                        ),
                        "minimum": 0,
                        "nullable": True,
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark one task as completed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Create a reminder for a course or task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_type": {"type": "string", "enum": ["course", "task"]},
                    "target_id": {"type": "string", "description": "Course or task ID"},
                    "advance_minutes": {"type": "integer", "description": "Lead time in minutes", "default": 15},
                },
                "required": ["target_type", "target_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "List reminders for the current user.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "Request a blocking confirmation, choice, or required missing information before writing/updating/deleting "
                "schedule, task, course, reminder, or memory data. Do not use for pure informational Q&A, concept "
                "explanations, exam-review answers, summaries, or optional follow-up offers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Question shown to the user"},
                    "type": {
                        "type": "string",
                        "enum": ["confirm", "select", "review"],
                        "description": "Interaction mode",
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Choices for select mode",
                    },
                    "data": {
                        "type": "object",
                        "description": (
                            "Structured payload shown to the user. Before any database write, include planned_operations "
                            "with the exact tool name and complete arguments that will execute after confirmation."
                        ),
                        "properties": {
                            "planned_operations": {
                                "type": "array",
                                "description": "Exact database write operations authorized by this confirmation.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "tool_name": {
                                            "type": "string",
                                            "enum": [
                                                "add_course",
                                                "update_course",
                                                "delete_course",
                                                "create_task",
                                                "update_task",
                                                "complete_task",
                                                "set_reminder",
                                                "save_period_times",
                                                "bulk_import_courses",
                                                "save_memory",
                                                "delete_memory",
                                            ],
                                        },
                                        "args": {
                                            "type": "object",
                                            "description": "Complete arguments for the write tool, including explicit null values.",
                                        },
                                    },
                                    "required": ["tool_name", "args"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                    },
                },
                "required": ["question", "type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "parse_schedule",
            "description": "Parse an uploaded spreadsheet schedule file and return recognized courses for confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "Temporary upload identifier returned by the schedule upload endpoint",
                    }
                },
                "required": ["file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "parse_schedule_image",
            "description": "Parse an uploaded schedule image and return recognized courses for confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "Temporary upload identifier returned by the schedule upload endpoint",
                    }
                },
                "required": ["file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_period_times",
            "description": "Save follow-up info for a parsed schedule upload, including period-time mapping and semester meta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "Temporary upload identifier returned by parse_schedule",
                    },
                    "term_id": {
                        "type": "string",
                        "description": "Term identifier, defaults to default",
                        "default": "default",
                    },
                    "entries": {
                        "type": "array",
                        "description": "Period-time pairs (optional if no missing periods)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "period": {"type": "string", "description": "e.g. 1-2"},
                                "time": {"type": "string", "description": "HH:MM-HH:MM"},
                            },
                            "required": ["period", "time"],
                        },
                    },
                    "semester_start_date": {
                        "type": "string",
                        "description": "Semester start date in YYYY-MM-DD format",
                    },
                    "term_total_weeks": {
                        "type": "integer",
                        "description": "Total teaching weeks in this semester, e.g. 16/18/20",
                        "minimum": 1,
                    },
                },
                "required": ["file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bulk_import_courses",
            "description": "Bulk import a confirmed list of courses into the user's schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "courses": {
                        "type": "array",
                        "description": "Confirmed course list",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Course name"},
                                "teacher": {"type": "string", "description": "Teacher"},
                                "location": {"type": "string", "description": "Location"},
                                "weekday": {"type": "integer", "description": "Weekday 1-7"},
                                "start_time": {"type": "string", "description": "Start time HH:MM"},
                                "end_time": {"type": "string", "description": "End time HH:MM"},
                                "week_start": {"type": "integer", "description": "Start week"},
                                "week_end": {"type": "integer", "description": "End week"},
                                "week_pattern": {
                                    "type": "string",
                                    "description": "Week recurrence pattern",
                                    "enum": ["all", "odd", "even"],
                                },
                                "week_text": {
                                    "type": "string",
                                    "description": "Human-readable week range",
                                },
                            },
                            "required": ["name", "weekday", "start_time", "end_time"],
                        },
                    }
                },
                "required": ["courses"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "Search long-term memories by keyword for the current user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword query for memory search"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save one long-term memory for the current user after user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["preference", "habit", "decision", "knowledge"],
                        "description": "Memory category",
                    },
                    "content": {"type": "string", "description": "Memory content to save"},
                },
                "required": ["category", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_memory",
            "description": "Delete one long-term memory by memory ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string", "description": "Memory ID"},
                },
                "required": ["memory_id"],
            },
        },
    },
]
