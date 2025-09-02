import React, { useState, useContext, useEffect, useCallback } from 'react';

import { JupyterFrontEnd } from '@jupyterlab/application';
import { DocumentWidget } from '@jupyterlab/docregistry';
import { FileEditor } from '@jupyterlab/fileeditor';
import { Notebook } from '@jupyterlab/notebook';

import { Widget } from '@lumino/widgets';
import { Signal } from '@lumino/signaling';
import type { Contents } from '@jupyterlab/services';
/**
 * ============================================================================
 * FILE MANAGER
 * ============================================================================
 */

type ICurrentFileInfo = {
  fileName: string;
  filePath: string;
};

export type IAvailableFile = {
  name: string;
  path: string;
  type: 'file' | 'directory';
};

/**
 * A manager that maintains information about the current file and provides
 * methods for accessing file content and getting available files.
 */
export class FileManager {
  /**
   * ====================== SETUP =================================
   */
  constructor(shell: JupyterFrontEnd.IShell, contents: Contents.IManager) {
    this._shell = shell;
    this._contents = contents;

    const onCurrentChanged = (
      sender: JupyterFrontEnd.IShell,
      args: { newValue: Widget | null }
    ) => {
      this._bindPathChangedFor(args.newValue ?? null);
      this._emitIfCurrentFileChanged();
    };

    this._shell.currentChanged?.connect(onCurrentChanged);
    this._cleanup.push(() => {
      this._shell.currentChanged?.disconnect(onCurrentChanged);
    });

    this._bindPathChangedFor(this._shell.currentWidget ?? null);
    this._emitIfCurrentFileChanged();
  }

  dispose(): void {
    this._activeCtxDisposer?.();
    this._activeCtxDisposer = null;
    this._cleanup.forEach(fn => fn());
    this._cleanup = [];
  }

  private _bindPathChangedFor(widget: Widget | null): void {
    // Unbind previous
    this._activeCtxDisposer?.();
    this._activeCtxDisposer = null;

    // Bind new
    if (widget && widget instanceof DocumentWidget) {
      const onPathChanged = () => this._emitIfCurrentFileChanged();
      widget.context?.pathChanged?.connect(onPathChanged);
      this._activeCtxDisposer = () =>
        widget.context?.pathChanged?.disconnect(onPathChanged);
    }
  }

  private _emitIfCurrentFileChanged(): void {
    const next = this.getCurrentFileInfo();
    if (this._currentFile?.filePath !== next?.filePath) {
      this._currentFile = next;
      this._currentFileChanged.emit(next ?? null);
    }
  }

  get currentFileChanged(): Signal<this, ICurrentFileInfo | null> {
    return this._currentFileChanged;
  }

  /**
   * ====================== CURRENT FILE HANDLER =================================
   */

  /**
   * Get current file information from the JupyterLab shell
   */
  getCurrentFileInfo(): ICurrentFileInfo | null {
    const currentWidget = this._shell.currentWidget;

    if (!(currentWidget instanceof DocumentWidget)) {
      return null;
    }

    const path = currentWidget?.context?.path;

    if (!path) {
      return null;
    }

    return {
      fileName: this._getDisplayFileName(path),
      filePath: path
    };
  }

  /**
   * Get the display name for a file based on its path
   */
  private _getDisplayFileName(filePath: string): string {
    return filePath.split('/').pop() || filePath;
  }

  /**
   * ====================== READ FILE HANDLER =================================
   */
  /**
   * Read content from a file using the shell
   */
  async readFileContent(filePath: string): Promise<string> {
    try {
      // If it's already open in an editor/notebook, prefer in-memory model
      const open = this._getOpenDocumentByPath(filePath);

      if (open) {
        const content = open.content;
        if (content instanceof FileEditor) {
          return content.model.sharedModel.getSource();
        } else if (content instanceof Notebook) {
          return this._notebookToPrettyString(content);
        }
      }

      // Not open -> fetch via Contents manager
      const model = await this._contents.get(filePath, { content: true });
      if (model.type === 'notebook') {
        return this._notebookModelToPrettyString(model.content as any);
      }
      // file/directory: for files with text, JLab sets model.format = 'text'
      // For binary, content will be base64 (format = 'base64')
      return (model.content as any) ?? '';
    } catch (error) {
      console.error('Error reading file content:', error);
      throw error;
    }
  }

  private _getOpenDocumentByPath(path: string): DocumentWidget | null {
    // Iterate main area widgets and match a DocumentWidget with context.path
    const widgets = this._shell.widgets('main');
    for (const w of widgets) {
      if (w instanceof DocumentWidget && w.context?.path === path) {
        return w;
      }
    }
    return null;
  }

  private _notebookToPrettyString(nb: Notebook): string {
    const model = nb.model;
    const cells = model?.cells;
    if (!cells) {
      return '';
    }
    const lines: string[] = [];
    for (let i = 0; i < cells.length; i++) {
      const cell = cells.get(i);
      const src = cell.sharedModel.getSource();
      const type = cell.type;
      if (type === 'markdown') {
        lines.push(`# Markdown Cell ${i + 1}\n${src}\n`);
      } else if (type === 'code') {
        lines.push(`# Code Cell ${i + 1}\n${src}\n`);
      } else {
        lines.push(`# Cell ${i + 1} (${type})\n${src}\n`);
      }
    }
    return lines.join('\n');
  }

  // Pretty string from nbformat JSON (model.content)
  private _notebookModelToPrettyString(nbjson: any): string {
    if (!nbjson || !Array.isArray(nbjson.cells)) {
      return '';
    }
    const lines: string[] = [];
    nbjson.cells.forEach((cell: any, idx: number) => {
      const type = cell.cell_type ?? 'unknown';
      const src = Array.isArray(cell.source)
        ? cell.source.join('')
        : cell.source ?? '';
      if (type === 'markdown') {
        lines.push(`# Markdown Cell ${idx + 1}\n${src}\n`);
      } else if (type === 'code') {
        lines.push(`# Code Cell ${idx + 1}\n${src}\n`);
      } else {
        lines.push(`# Cell ${idx + 1} (${type})\n${src}\n`);
      }
    });
    return lines.join('\n');
  }

  /**
   * ====================== AVAILABLE FILES HANDLER =================================
   */
  /**
   * Get available files in the workspace for selection
   */
  async getAvailableFiles(): Promise<IAvailableFile[]> {
    const out: IAvailableFile[] = [];

    try {
      // Get open documents from the shell
      const enqueueDir = async (path: string) => {
        const model = await this._contents.get(path, { content: true });
        if (model.type === 'directory' && Array.isArray(model.content)) {
          for (const entry of model.content as Contents.IModel[]) {
            out.push({
              name: this._getDisplayFileName(entry.path),
              path: entry.path,
              type: entry.type === 'directory' ? 'directory' : 'file'
            });
            if (entry.type === 'directory') {
              await enqueueDir(entry.path);
            }
          }
        }
      };

      // Root listing: '' is the root for the default drive
      await enqueueDir('');
      return out;
    } catch (error) {
      console.error('Error getting available files:', error);
      return [];
    }
  }

  protected _shell: JupyterFrontEnd.IShell;
  protected _contents: Contents.IManager;

  protected _currentFile: ICurrentFileInfo | null = null;
  protected _currentFileChanged = new Signal<this, ICurrentFileInfo | null>(
    this
  );

  protected _activeCtxDisposer: (() => void) | null = null;
  protected _cleanup: Array<() => void> = [];
}

/**
 * ============================================================================
 * FILE CONTEXT PROVIDER
 * ============================================================================
 */

type FileContextReturn = {
  currentFile: ICurrentFileInfo | null;
  manager: FileManager;
  getAvailableFiles: () => Promise<IAvailableFile[]>;
  readFileContent: (filePath: string) => Promise<string>;
};

type FileContextValue = {
  currentFile: ICurrentFileInfo | null;
  manager: FileManager | null;
};

const defaultFileContext: FileContextValue = {
  currentFile: null,
  manager: null
};

const FileContext = React.createContext<FileContextValue>(defaultFileContext);

type FileContextProps = {
  fileManager: FileManager;
  children: React.ReactNode;
};

export function FileContextProvider(props: FileContextProps): JSX.Element {
  const [currentFile, setCurrentFile] = useState<ICurrentFileInfo | null>(null);

  useEffect(() => {
    const manager = props.fileManager;

    // Initialize current file
    setCurrentFile(manager.getCurrentFileInfo());

    // Subscribe/Listen for current file changes
    const onFileChange = (
      _: FileManager,
      newCurrentFile: ICurrentFileInfo | null
    ) => {
      setCurrentFile(newCurrentFile);
    };
    manager.currentFileChanged.connect(onFileChange);

    return () => {
      manager.currentFileChanged.disconnect(onFileChange);
    };
  }, [props.fileManager]);

  return (
    <FileContext.Provider
      value={{
        currentFile,
        manager: props.fileManager
      }}
    >
      {props.children}
    </FileContext.Provider>
  );
}

/**
 * Usage: `const fileContext = useFileContext()`
 *
 * Returns an object `fileContext` with the following properties:
 * - `fileContext.currentFile`: information about the current file (or null)
 * - `fileContext.manager`: the `FileManager` singleton
 * - `fileContext.getAvailableFiles`: function to get available files
 * - `fileContext.readFileContent`: function to read file content
 */
export function useFileContext(): FileContextReturn {
  const { currentFile, manager } = useContext(FileContext);

  if (!manager) {
    throw new Error(
      'useFileContext() cannot be called outside FileContextProvider.'
    );
  }

  const getAvailableFiles = useCallback(async () => {
    return manager.getAvailableFiles();
  }, [manager]);

  const readFileContent = useCallback(
    async (filePath: string) => {
      return manager.readFileContent(filePath);
    },
    [manager]
  );

  return {
    currentFile,
    manager,
    getAvailableFiles,
    readFileContent
  };
}
