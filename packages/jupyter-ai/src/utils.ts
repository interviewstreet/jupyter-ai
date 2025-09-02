/**
 * Contains various utility functions shared throughout the project.
 */
import { Notebook } from '@jupyterlab/notebook';
import { FileEditor } from '@jupyterlab/fileeditor';
import { CodeEditor } from '@jupyterlab/codeeditor';
import { Widget } from '@lumino/widgets';

/**
 * Get text selection from an editor widget (DocumentWidget#content).
 */
export function getTextSelection(widget: Widget): string {
  const editor = getEditor(widget);
  if (!editor) {
    return '';
  }

  const selectionObj = editor.getSelection();
  const start = editor.getOffsetAt(selectionObj.start);
  const end = editor.getOffsetAt(selectionObj.end);
  const text = editor.model.sharedModel.getSource().substring(start, end);

  return text;
}

/**
 * Get editor instance from an editor widget (i.e. `DocumentWidget#content`).
 */
export function getEditor(
  widget: Widget
): CodeEditor.IEditor | null | undefined {
  let editor: CodeEditor.IEditor | null | undefined;
  if (widget instanceof FileEditor) {
    editor = widget.editor;
  } else if (widget instanceof Notebook) {
    editor = widget.activeCell?.editor;
  }

  return editor;
}

/**
 * Gets the index of the cell associated with `cellId`.
 */
export function getCellIndex(notebook: Notebook, cellId: string): number {
  const idx = notebook.model?.sharedModel.cells.findIndex(
    cell => cell.getId() === cellId
  );
  return idx === undefined ? -1 : idx;
}

/**
 * Obtain the provider ID component from a model ID.
 */
export function getProviderId(globalModelId: string): string | null {
  if (!globalModelId) {
    return null;
  }

  return globalModelId.split(':')[0];
}

/**
 * Obtain the model name component from a model ID.
 */
export function getModelLocalId(globalModelId: string): string | null {
  if (!globalModelId) {
    return null;
  }

  const components = globalModelId.split(':').slice(1);
  return components.join(':');
}

/**
 * Generate a unique identifier using crypto.randomUUID() if available,
 * falling back to a timestamp-based approach for older environments.
 */
export function generateUniqueId(): string {
  // Use crypto.randomUUID() if available (modern browsers)
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }

  // Fallback for older environments: timestamp + random number
  return `${Date.now()}-${Math.random().toString(36).substring(2, 15)}`;
}
