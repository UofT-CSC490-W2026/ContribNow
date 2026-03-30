import type { TaskType } from "../types";

interface TaskSelectorProps {
  value: TaskType | undefined;
  description: string | undefined;
  onChange: (taskType: TaskType | undefined, description: string | undefined) => void;
}

const TASK_OPTIONS: { value: TaskType; label: string }[] = [
  { value: "fix_bug", label: "Fix a bug" },
  { value: "add_feature", label: "Add a new feature" },
  { value: "update_docs", label: "Update documentation" },
  { value: "understand", label: "Understand the codebase" },
  { value: "other", label: "Something else" },
];

export function TaskSelector({ value, description, onChange }: TaskSelectorProps) {
  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-gray-700">What are you trying to do?</p>
      <div className="space-y-2">
        {TASK_OPTIONS.map((opt) => (
          <label key={opt.value} className="flex cursor-pointer items-center gap-2.5">
            <input
              type="radio"
              name="task-type"
              value={opt.value}
              checked={value === opt.value}
              onChange={() => onChange(opt.value, description)}
              className="h-4 w-4 border-gray-300 text-purple-600 focus:ring-purple-500"
            />
            <span className="text-sm text-gray-700">{opt.label}</span>
          </label>
        ))}
      </div>

      {value === "other" && (
        <textarea
          value={description ?? ""}
          onChange={(e) => onChange(value, e.target.value || undefined)}
          placeholder="Describe what you're trying to do..."
          rows={2}
          className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-purple-500 focus:ring-1 focus:ring-purple-500 focus:outline-none"
        />
      )}
    </div>
  );
}
