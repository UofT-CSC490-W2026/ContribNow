import { useState } from "react";

const STORAGE_KEY = "contribnow_access_key";

export function useAccessKey(): [string, (key: string) => void] {
  const [accessKey, setAccessKey] = useState(
    () => localStorage.getItem(STORAGE_KEY) ?? ""
  );

  const updateAccessKey = (key: string) => {
    setAccessKey(key);
    localStorage.setItem(STORAGE_KEY, key);
  };

  return [accessKey, updateAccessKey];
}
