import { App } from 'antd';
import { useCallback, useRef } from 'react';

/**
 * Provides promise-based replacements for window.alert(), window.confirm(),
 * and window.prompt() using Ant Design's modal and message APIs.
 *
 * Usage:
 *   const { showAlert, showConfirm, showPrompt } = useDialog();
 *   showAlert('Something went wrong', 'error');
 *   if (await showConfirm('Delete this record?')) { ... }
 *   const reason = await showPrompt('Reason for rejection:');
 */
export function useDialog() {
    const { modal, message } = App.useApp();

    const showAlert = useCallback(
        (msg: string, type: 'error' | 'warning' | 'success' | 'info' = 'error') => {
            message[type](msg);
        },
        [message],
    );

    const showConfirm = useCallback(
        (content: string, title = 'Confirm'): Promise<boolean> => {
            return new Promise((resolve) => {
                modal.confirm({
                    title,
                    content,
                    okText: 'Yes',
                    cancelText: 'No',
                    onOk: () => resolve(true),
                    onCancel: () => resolve(false),
                });
            });
        },
        [modal],
    );

    const showPrompt = useCallback(
        (content: string, title = 'Input Required', defaultValue = ''): Promise<string | null> => {
            return new Promise((resolve) => {
                let value = defaultValue;
                modal.confirm({
                    title,
                    content: (
                        <div>
                            <p style={{ marginBottom: 8 }}>{content}</p>
                            <input
                                type="text"
                                defaultValue={defaultValue}
                                onChange={(e) => { value = e.target.value; }}
                                autoFocus
                                style={{
                                    width: '100%',
                                    padding: '8px 12px',
                                    borderRadius: '6px',
                                    border: '1px solid #d9d9d9',
                                    fontSize: '14px',
                                }}
                            />
                        </div>
                    ),
                    okText: 'OK',
                    cancelText: 'Cancel',
                    onOk: () => resolve(value || null),
                    onCancel: () => resolve(null),
                });
            });
        },
        [modal],
    );

    return { showAlert, showConfirm, showPrompt };
}
