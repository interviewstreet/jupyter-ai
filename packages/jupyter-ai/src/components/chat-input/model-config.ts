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
    llm: 'claude-3-opus-20240229',
    label: 'claude-3-opus-20240229'
  },
  {
    llm: 'claude-3.5-sonnet-20241022',
    label: 'claude-3-5-sonnet-20241022'
  },
  {
    llm: 'gpt-4o',
    label: 'gpt-4o'
  },
  {
    llm: 'gpt-4',
    label: 'gpt-4'
  },
  {
    llm: 'gpt-4-turbo',
    label: 'gpt-4-turbo'
  },
  {
    llm: 'gemini-2.5-flash',
    label: 'gemini-2.5-flash'
  },
  {
    llm: 'gemini-2.5-pro',
    label: 'gemini-2.5-pro'
  }
];
