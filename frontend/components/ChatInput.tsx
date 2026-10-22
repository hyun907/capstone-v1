"use client";

import { useState, type FormEvent } from "react";

interface ChatInputProps {
  disabled: boolean;
  onSend: (message: string) => void;
}

export function ChatInput({ disabled, onSend }: ChatInputProps) {
  const [value, setValue] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = value.trim();
    if (!message || disabled) return;
    onSend(message);
    setValue("");
  }

  return (
    <form className="chat-input" onSubmit={handleSubmit}>
      <label className="sr-only" htmlFor="message-input">메시지</label>
      <input
        id="message-input"
        autoComplete="off"
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        placeholder={disabled ? "답변을 만들고 있습니다…" : "운영 상황이나 절차를 물어보세요"}
        value={value}
      />
      <button disabled={disabled || !value.trim()} type="submit">전송</button>
    </form>
  );
}
