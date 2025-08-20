import {
    JupyterFrontEnd,
    JupyterFrontEndPlugin
  } from '@jupyterlab/application';
  import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';
  import { CodeCell } from '@jupyterlab/cells';
  import { ToolbarButton } from '@jupyterlab/apputils';
  import { Widget } from '@lumino/widgets'; // <-- added
  import { CommandIDs } from '../index';
  
  /** Extract error information from a CodeCell */
  function getErrorFromCell(cell: CodeCell): any {
    const outputs = cell.model.outputs;
    for (let i = 0; i < outputs.length; i++) {
      const out: any = (outputs.get(i) as any)?.toJSON?.() ?? outputs.get(i);
      if (out && out.output_type === 'error') {
        return {
          name: out.ename || 'Error',
          value: out.evalue || '',
          traceback: out.traceback || []
        };
      }
    }
    return null;
  }
  
  const WIRED = new WeakSet<CodeCell>();
  const BUTTONS = new WeakMap<CodeCell, ToolbarButton>(); // <-- added
  
  function cellHasError(cell: CodeCell): boolean {
    const outs = cell.model.outputs;
    for (let i = 0; i < outs.length; i++) {
      if ((outs.get(i) as any)?.type === 'error') return true;
    }
    return false;
  }
  
  function ensureButton(cell: CodeCell, app: JupyterFrontEnd): ToolbarButton {
    console.log("call to add buttn")
    const btn = new ToolbarButton({
      label: 'Explain error',
      tooltip: 'Ask Jupyter AI to explain this error',
      onClick: () => {
        // Focus chat input if available
        try {
          app.commands.execute(CommandIDs.focusChatInput);
        } catch {}
  
        // Optionally pass the error to a command; otherwise just log
        const errorOutput = getErrorFromCell(cell);
        if (errorOutput) {
          try {
            // Only if you have such a command wired up
            // @ts-ignore – optional command
            app.commands.execute(CommandIDs.explainError, { error: errorOutput });
          } catch {
            console.log('Error found in cell:', errorOutput);
          }
        }
      }
    });
    btn.addClass('jupyter-ai-error-button');
  
    // Attach in the cell header (DOM-based, version-safe)
    const headerNode = cell.node.getElementsByClassName('jp-CellHeader')[0] as HTMLElement | null;
    console.log('-->', cell, cell.node, cell.node.getElementsByClassName('jp-CellHeader'))
    console.log('Cell node:', cell.node);
    console.log('Cell classes:', cell.node.className);
    console.log('Is CodeCell?', cell.node.classList.contains('jp-CellHeader'));
    console.log('headerNode', headerNode)
  
    if (headerNode) {
      Widget.attach(btn, headerNode);
    } else {
      // Fallbacks for older/custom builds
      const anyCell = cell as any;
      if (anyCell.toolbar?.addItem) {
        anyCell.toolbar.addItem('jupyter-ai-error-button', btn);
      } else if (anyCell.header?.addWidget) {
        anyCell.header.addWidget(btn);
      }
    }
  
  
    // app.docRegistry.addWidgetExtension('Notebook', {
    //   createNew: () => btn,
    // });
  
    // Clean up when the cell is disposed
    cell.disposed.connect(() => {
      try {
        btn?.dispose();
      } finally {
        BUTTONS.delete(cell);
      }
    });
  
    return btn;
  }
  
  /** Create (and wire) the conditional button for a given CodeCell */
  function wireCell(cell: CodeCell, app: JupyterFrontEnd): void {
    if (WIRED.has(cell)) return;
    WIRED.add(cell);
  
    // Show/hide based on whether the cell has an error
    const updateVisibility = () => {
      const hasError = cellHasError(cell);
      const id: string | undefined = (cell.model as any).id;
  
      // Cell source text. Prefer sharedModel.getSource(); fall back to value.text.
      const source: string =
        (cell.model as any).sharedModel?.getSource?.() ??
        (cell.model as any).value?.text ??
        '';
    
      console.log('Update->', id, source, hasError, cell);
  
      let btn = BUTTONS.get(cell);
      console.log("Button", btn , btn?.isDisposed)
      if (!btn || btn.isDisposed) {
        btn = ensureButton(cell, app);
        BUTTONS.set(cell, btn);
      }
      if (hasError) {
        console.log('showinf',hasError, btn)
        btn.show();
      } else {
        btn?.hide();
      }
    };
  
    // Initial state + react to future output changes
    updateVisibility();
    cell.model.outputs.changed.connect(updateVisibility);
  
    // Clean up when the cell is disposed
    cell.disposed.connect(() => {
      try {
        cell.model.outputs.changed.disconnect(updateVisibility);
      } catch {}
    });
  }
  
  /** Wire all current & future cells in a NotebookPanel */
  function instrumentNotebook(panel: NotebookPanel, app: JupyterFrontEnd): void {
    const notebook = panel.content;
  
    const wireAll = () => {
      notebook.widgets.forEach(w => {
        if (w instanceof CodeCell) wireCell(w, app);
      });
    };
  
    const onCellsChanged = (_: any, change: any) => {
      if (change.type === 'add' || change.type === 'set') {
        const count = change.newValues?.length ?? 1;
        // Wait for view to materialize widgets for new models
        requestAnimationFrame(() => {
          for (let i = 0; i < count; i++) {
            const w = notebook.widgets[change.newIndex + i];
            if (w instanceof CodeCell) wireCell(w, app);
          }
        });
      }
      // 'remove' and 'move' need no action; cells clean themselves up on dispose
    };
  
    // Initial wiring only after the panel is ready & shown
    void (async () => {
      await panel.context.ready;
      await panel.revealed;
      wireAll();
      notebook.model?.cells.changed.connect(onCellsChanged as any);
    })();
  
    // Full model swap (reload/restore): rewire once
    notebook.modelChanged.connect(() => {
      requestAnimationFrame(() => {
        wireAll();
        notebook.model?.cells.changed.disconnect(onCellsChanged as any);
        notebook.model?.cells.changed.connect(onCellsChanged as any);
      });
    });
  }
  
  export const errorButtonPlugin: JupyterFrontEndPlugin<void> = {
    id: 'jupyter-ai:error-button-plugin',
    autoStart: true,
    requires: [INotebookTracker],
    activate: (app: JupyterFrontEnd, tracker: INotebookTracker) => {
      tracker.widgetAdded.connect((_, panel) => instrumentNotebook(panel, app));
      tracker.forEach(panel => instrumentNotebook(panel, app));
    }
  };
  