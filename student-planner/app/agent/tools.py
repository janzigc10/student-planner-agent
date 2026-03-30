"""Tool definitions for LLM function calling."""

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_courses",
            "description": "查看用户当前的所有课程。返回课程列表，包含课程名、教师、地点、时间、周次。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_course",
            "description": "添加一门课程到用户课表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "课程名称"},
                    "teacher": {"type": "string", "description": "教师姓名"},
                    "location": {"type": "string", "description": "上课地点"},
                    "weekday": {
                        "type": "integer",
                        "description": "周几上课，1=周一，7=周日",
                        "minimum": 1,
                        "maximum": 7,
                    },
                    "start_time": {
                        "type": "string",
                        "description": "开始时间，格式 HH:MM",
                        "pattern": "^\\d{2}:\\d{2}$",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间，格式 HH:MM",
                        "pattern": "^\\d{2}:\\d{2}$",
                    },
                    "week_start": {"type": "integer", "description": "开始周次", "default": 1},
                    "week_end": {"type": "integer", "description": "结束周次", "default": 16},
                },
                "required": ["name", "weekday", "start_time", "end_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_course",
            "description": "删除一门课程。",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "课程ID"},
                },
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_free_slots",
            "description": "查询指定日期范围内用户的空闲时间段。返回每天的空闲时段列表，精确到分钟。已排除课程和已安排的任务。在安排任何新任务之前必须先调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "开始日期，格式 YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "结束日期，格式 YYYY-MM-DD"},
                    "min_duration_minutes": {
                        "type": "integer",
                        "description": "最短有效时段（分钟），默认30",
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
            "description": "根据考试列表和可用时间，生成复习计划。返回结构化的任务列表。必须先调用 get_free_slots 获取可用时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "exams": {
                        "type": "array",
                        "description": "考试列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "course_name": {"type": "string"},
                                "exam_date": {"type": "string", "description": "格式 YYYY-MM-DD"},
                                "difficulty": {
                                    "type": "string",
                                    "enum": ["easy", "medium", "hard"],
                                },
                            },
                            "required": ["course_name", "exam_date"],
                        },
                    },
                    "available_slots": {
                        "type": "object",
                        "description": "get_free_slots 的返回结果",
                    },
                    "strategy": {
                        "type": "string",
                        "enum": ["balanced", "intensive", "spaced"],
                        "description": "复习策略：balanced=均衡, intensive=考前密集, spaced=间隔重复",
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
            "name": "list_tasks",
            "description": "查看指定日期范围内的任务列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "开始日期，格式 YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "结束日期，格式 YYYY-MM-DD"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "修改一个已有的任务（时间、标题、状态等）。修改时间前应先用 get_free_slots 检查目标时段是否空闲。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务ID"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "scheduled_date": {"type": "string", "description": "格式 YYYY-MM-DD"},
                    "start_time": {"type": "string", "description": "格式 HH:MM"},
                    "end_time": {"type": "string", "description": "格式 HH:MM"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "completed", "skipped"],
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
            "description": "标记一个任务为已完成。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务ID"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "为课程或任务设置提醒。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_type": {"type": "string", "enum": ["course", "task"]},
                    "target_id": {"type": "string", "description": "课程或任务的ID"},
                    "advance_minutes": {
                        "type": "integer",
                        "description": "提前多少分钟提醒",
                        "default": 15,
                    },
                },
                "required": ["target_type", "target_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "查看用户的所有提醒。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "向用户展示信息并请求确认或选择。用于关键操作前的确认。不要连续调用两次 ask_user，中间至少做一步实际操作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "要问用户的问题"},
                    "type": {
                        "type": "string",
                        "enum": ["confirm", "select", "review"],
                        "description": "confirm=是否确认, select=从选项中选, review=展示计划请求确认",
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "选项列表（select类型时必填）",
                    },
                    "data": {"type": "object", "description": "需要展示给用户的结构化数据"},
                },
                "required": ["question", "type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "parse_schedule",
            "description": "Parse an uploaded Excel/WPS schedule file and return recognized courses for user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "Temporary upload identifier returned by /api/schedule/upload"
                    }
                },
                "required": ["file_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "parse_schedule_image",
            "description": "Parse an uploaded schedule image and return recognized courses for user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "Temporary upload identifier returned by /api/schedule/upload"
                    }
                },
                "required": ["file_id"]
            }
        }
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
                                "week_end": {"type": "integer", "description": "End week"}
                            },
                            "required": ["name", "weekday", "start_time", "end_time"]
                        }
                    }
                },
                "required": ["courses"]
            }
        }
    },]