import { scaleRgba } from './utils.js';

const charts = [];
const chartAnimationDuration = 100;  // ms
let commandColors, commandLabels;
const initVal = 0.2;

export const createCharts = (_commandColors, _commandLabels) => {
    if (charts.length > 0) removeCharts(); // remove existing charts

    commandColors = _commandColors;
    commandLabels = _commandLabels;

    [...document.getElementsByClassName('likelihood-chart')].forEach((canvas) => {
        // create a config for each chart so that they don't share the same data
        const config = {
            type: 'bar',
            data: {
                labels: Array(commandLabels.length).fill(''),  // neccesary
                datasets: [{
                    data: Array(commandLabels.length).fill(initVal),
                    backgroundColor: commandColors,
                    borderColor: commandColors.map(rgba => scaleRgba(rgba, 0.7, 1)),
                    borderWidth: 1,
                }]
            },
            options: {
                plugins: {
                    legend: {
                        display: false,
                    },
                    annotation: {
                        annotations: {
                            lineThres: {
                                type: 'line',
                                yMin: 1,
                                yMax: 1,
                                borderColor: 'black',
                                borderWidth: 1,
                                borderDash: [4, 4], // dashed line style
                            }
                        }
                    },
                },
                scales: {
                    x: {
                        ticks: {
                            display: false,
                        },
                        grid: {
                            display: false,
                        }
                    },
                    y: {
                        beginAtZero: true,
                        max: 1.4,
                        ticks: {
                            display: false,
                            // display: true,
                            // stepSize: 0.1,
                            // callback: (value) => [0, 0.3, 1].includes(value) ? value : '',
                        },
                        grid: {
                            display: false,
                        }
                    },
                },
                animation: {
                    duration: chartAnimationDuration,
                },
                maintainAspectRatio: false,
                backgroundColor: 'white',
                isBarLocked: Array(commandLabels.length).fill(false),
            },
        };
        const chart = new Chart(canvas.getContext('2d'), config);
        chart.update();
        charts.push(chart);
        canvas.parentElement.style.display = 'block';  // show the parent container
    });
}

const removeCharts = () => {
    while (charts.length > 0) {
        const chart = charts.pop();
        chart.canvas.parentElement.style.display = 'none';
        chart.destroy();
    }
};

export const updateChartLock = (agentId, nextAcceptableCommands) => {
    const chart = charts[agentId];
    if (chart === undefined) return;
    chart.options.isBarLocked = commandLabels.map(command => !nextAcceptableCommands.includes(command));
    chart.update();
}

export const updateChartData = (agentId, likelihoods) => {
    const chart = charts[agentId];
    if (chart === undefined) return;
    // update only the unlocked bars
    likelihoods.forEach((lik, i) => {
        if (!chart.options.isBarLocked[i]) chart.data.datasets[0].data[i] = lik;
    });
    chart.update();
}

export const resetChartData = () => {
    charts.forEach(chart => {
        chart.data.datasets[0].data = Array(commandLabels.length).fill(initVal);
        chart.update();
    });
}

export const updateChartColor = (agentId, currentCommand, username) => {
    const chart = charts[agentId];
    if (chart === undefined) return;  // occurs when the environment is reset on page load
    chart.data.datasets[0].backgroundColor = [...Array(commandLabels.length).keys()].map(barId => getBarColor(barId, currentCommand));
    chart.data.datasets[0].borderColor = [...Array(commandLabels.length).keys()].map(barId => getBorderColor(barId, currentCommand, chart.options.isBarLocked));
    chart.update();
    if (currentCommand === null) {
        document.getElementById(`variable_${agentId}`).textContent = ``;
    } else {
        document.getElementById(`variable_${agentId}`).textContent = ` ${username}`;
    };
};

const getBarColor = (barId, currentCommand) => {
    // highlight the current command bar
    if (commandLabels[barId] === currentCommand) return scaleRgba(commandColors[barId], 1, 1);
    // nothing for border color
    return commandColors[barId];
}

const getBorderColor = (barId, currentCommand, isBarLocked) => {
    // add black border to the current command bar
    if (commandLabels[barId] === currentCommand) return 'rgba(0, 0, 0, 1)';
    // remove border from the locked bars
    if (isBarLocked[barId]) return 'rgba(255, 255, 255, 1)';
    // else set the original color
    return scaleRgba(commandColors[barId], 0.7, 1);
}
