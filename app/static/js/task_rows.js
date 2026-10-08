// Los enlaces también funcionan con teclado y sin JavaScript.
document.addEventListener('click', function (event) {
    const row = event.target.closest('.task-row[data-task-url], .payment-row[data-payment-url]');
    if (!row || event.target.closest('a, button, input, select, textarea') ||
        event.ctrlKey || event.metaKey || event.shiftKey || event.altKey ||
        window.getSelection().toString()) return;
    window.location.assign(row.dataset.taskUrl || row.dataset.paymentUrl);
});
