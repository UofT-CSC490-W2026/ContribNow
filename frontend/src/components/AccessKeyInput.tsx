import { useState } from "react";

interface AccessKeyInputProps {
  value: string;
  onChange: (key: string) => void;
}

export function AccessKeyInput({ value, onChange }: AccessKeyInputProps) {
  const [visible, setVisible] = useState(false);

  return (
    <div>
      <label
        htmlFor="access-key"
        className="block text-sm font-medium text-gray-700"
      >
        Access Key
      </label>
      <div className="relative mt-1">
        <input
          id="access-key"
          type={visible ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Enter your access key"
          className="block w-full rounded-lg border border-gray-300 px-3 py-2 pr-16 text-sm shadow-sm focus:border-purple-500 focus:ring-1 focus:ring-purple-500 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => setVisible(!visible)}
          className="absolute inset-y-0 right-0 flex items-center px-3 text-xs text-gray-500 hover:text-gray-700"
        >
          {visible ? "Hide" : "Show"}
        </button>
      </div>
    </div>
  );
}
