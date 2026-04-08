'use client';

import { useChat } from '@ai-sdk/react';
import { useRef, useEffect, useState } from 'react';

function getTextContent(message: { parts?: { type: string; text?: string }[]; content?: string }): string {
  if (message.parts) {
    return message.parts
      .filter((p) => p.type === 'text')
      .map((p) => p.text || '')
      .join('');
  }
  return message.content || '';
}

const SUGGESTIONS = [
  '가상 DOM이 뭐야?',
  'React vs Vue 비교해줘',
  'TCP와 UDP 차이점은?',
  'Spring Boot DI 설명해줘',
  '이벤트 루프란?',
  'Docker vs 가상머신?',
  'Redis를 캐시로 쓰는 이유?',
  '인덱스를 걸면 왜 빨라져?',
];

export default function Home() {
  const { messages, sendMessage, status } = useChat();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue] = useState('');
  const isLoading = status === 'streaming' || status === 'submitted';

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isLoading) return;
    sendMessage({ text: inputValue });
    setInputValue('');
  };

  const handleSuggestion = (q: string) => {
    sendMessage({ text: q });
  };

  return (
    <div className="flex flex-col h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-slate-900 text-white px-6 py-4 shadow-lg">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold tracking-tight">면접위키 RAG</h1>
            <p className="text-slate-400 text-xs mt-0.5">AI 면접 준비 질의응답</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-green-400"></span>
            <span className="text-xs text-slate-400">온라인</span>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
          {/* Empty state */}
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16">
              <div className="w-16 h-16 bg-slate-900 rounded-2xl flex items-center justify-center mb-6">
                <span className="text-2xl">Q</span>
              </div>
              <h2 className="text-xl font-semibold text-slate-800 mb-2">무엇이든 물어보세요</h2>
              <p className="text-slate-500 text-sm mb-8 text-center">
                CS 기초, 프레임워크, 데이터베이스 등<br />면접 관련 기술 질문에 답변합니다
              </p>
              <div className="flex flex-wrap justify-center gap-2 max-w-lg">
                {SUGGESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => handleSuggestion(q)}
                    className="px-3 py-1.5 bg-white border border-slate-200 rounded-full text-xs text-slate-600 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-all duration-200"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Chat messages */}
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {m.role !== 'user' && (
                <div className="w-7 h-7 bg-slate-900 rounded-lg flex items-center justify-center mr-2 mt-1 flex-shrink-0">
                  <span className="text-white text-xs font-bold">AI</span>
                </div>
              )}
              <div
                className={`max-w-[75%] rounded-2xl px-4 py-3 ${
                  m.role === 'user'
                    ? 'bg-slate-900 text-white'
                    : 'bg-white border border-slate-200 text-slate-800 shadow-sm ai-message'
                }`}
              >
                <div className="whitespace-pre-wrap text-sm leading-relaxed">
                  {getTextContent(m)}
                </div>
              </div>
            </div>
          ))}

          {/* Loading */}
          {isLoading && messages[messages.length - 1]?.role === 'user' && (
            <div className="flex justify-start">
              <div className="w-7 h-7 bg-slate-900 rounded-lg flex items-center justify-center mr-2 mt-1 flex-shrink-0">
                <span className="text-white text-xs font-bold">AI</span>
              </div>
              <div className="bg-white border border-slate-200 rounded-2xl px-4 py-3 shadow-sm">
                <div className="dot-bounce flex space-x-1.5">
                  <span className="w-2 h-2 bg-slate-400 rounded-full inline-block"></span>
                  <span className="w-2 h-2 bg-slate-400 rounded-full inline-block"></span>
                  <span className="w-2 h-2 bg-slate-400 rounded-full inline-block"></span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-slate-200 bg-white px-4 py-3">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto flex gap-2">
          <input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="면접 질문을 입력하세요..."
            className="flex-1 border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent placeholder:text-slate-400"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !inputValue.trim()}
            className="bg-slate-900 text-white px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            전송
          </button>
        </form>
      </div>

      {/* Footer */}
      <div className="bg-slate-50 border-t border-slate-100 px-4 py-2 text-center">
        <p className="text-[10px] text-slate-400">적대적 검증 설계 기반 RAG 시스템 | 면접위키</p>
      </div>
    </div>
  );
}