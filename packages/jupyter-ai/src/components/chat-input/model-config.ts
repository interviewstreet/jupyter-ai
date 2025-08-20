export type ModelOption = {
  llm: string;
  label: string;
};

export const DEFAULT_MODEL_OPTIONS: ModelOption[] = [
  {
    llm: 'claude-4-sonnet',
    label: 'claude-4-sonnet'
  },
  {
    llm: 'claude-4-opus',
    label: 'claude-4-opus'
  },
  {
    llm: 'claude-3.7-sonnet',
    label: 'claude-3.7-sonnet'
  },
  {
    llm: 'claude-3.5-sonnet',
    label: 'claude-3.5-sonnet'
  },
  {
    llm: 'gpt-4o',
    label: 'gpt-4o'
  },
  {
    llm: 'gpt-4.1',
    label: 'gpt-4.1'
  },
  {
    llm: 'o4-mini',
    label: 'o4-mini'
  },
  {
    llm: 'o3-mini',
    label: 'o3-mini'
  },
  {
    llm: 'gemini-2.5-pro',
    label: 'gemini-2.5-pro'
  }
];
