'use client';

import { useRef, useEffect, useState, useCallback } from 'react';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
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
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isLoading) return;

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: text };
    const assistantMsg: Message = { id: (Date.now() + 1).toString(), role: 'assistant', content: '' };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setInputValue('');
    setIsLoading(true);

    try {
      const allMessages = [...messages, userMsg].map(m => ({
        role: m.role,
        content: m.content,
      }));

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: allMessages }),
      });

      if (!res.ok) throw new Error(`서버 오류: ${res.status}`);

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        setMessages(prev => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === 'assistant') {
            updated[updated.length - 1] = { ...last, content: last.content + chunk };
          }
          return updated;
        });
      }
    } catch (err) {
      setMessages(prev => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last.role === 'assistant') {
          updated[updated.length - 1] = { ...last, content: `오류: ${err}` };
        }
        return updated;
      });
    } finally {
      setIsLoading(false);
    }
  }, [messages, isLoading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(inputValue);
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
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16">
              <div className="w-16 h-16 bg-slate-900 rounded-2xl flex items-center justify-center mb-6">
                <span className="text-2xl text-white">Q</span>
              </div>
              <h2 className="text-xl font-semibold text-slate-800 mb-2">무엇이든 물어보세요</h2>
              <p className="text-slate-500 text-sm mb-8 text-center">
                CS 기초, 프레임워크, 데이터베이스 등<br />면접 관련 기술 질문에 답변합니다
              </p>
              <div className="flex flex-wrap justify-center gap-2 max-w-lg">
                {SUGGESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => sendMessage(q)}
                    className="px-3 py-1.5 bg-white border border-slate-200 rounded-full text-xs text-slate-600 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-all duration-200"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

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
                    : 'bg-white border border-slate-200 text-slate-800 shadow-sm'
                }`}
              >
                <div className="whitespace-pre-wrap text-sm leading-relaxed">
                  {m.content || (m.role === 'assistant' && isLoading ? '' : m.content)}
                </div>
              </div>
            </div>
          ))}

          {isLoading && messages[messages.length - 1]?.content === '' && (
            <div className="flex justify-start">
              <div className="w-7 h-7 bg-slate-900 rounded-lg flex items-center justify-center mr-2 mt-1 flex-shrink-0">
                <span className="text-white text-xs font-bold">AI</span>
              </div>
              <div className="bg-white border border-slate-200 rounded-2xl px-4 py-3 shadow-sm">
                <div className="flex space-x-1.5">
                  <span className="w-2 h-2 bg-slate-400 rounded-full inline-block animate-bounce" style={{ animationDelay: '0ms' }}></span>
                  <span className="w-2 h-2 bg-slate-400 rounded-full inline-block animate-bounce" style={{ animationDelay: '150ms' }}></span>
                  <span className="w-2 h-2 bg-slate-400 rounded-full inline-block animate-bounce" style={{ animationDelay: '300ms' }}></span>
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
